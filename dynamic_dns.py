#  Copyright (c) 2025-2026 André S. Gomes
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  SPDX-License-Identifier: Apache-2.0

# Python 3.9 (UniFi OS) can't evaluate "str | None" annotations without this
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import sys
import requests
import requests.adapters
import urllib3

# Define required environment variables for each provider
REQUIRED_ENV_VARIABLES = {
    "HE": [
        "HE_HOSTNAME",
        "HE_PASSWORD",
        "UNIFI_API_USERNAME",
        "UNIFI_API_PASSWORD"
    ],
    "Cloudflare": [
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ZONE_ID",
        "CLOUDFLARE_RECORD_NAME",
        "UNIFI_API_USERNAME",
        "UNIFI_API_PASSWORD"
    ],
    "DynDNS": [
        "DYNDNS_UPDATE_URL",
        "DYNDNS_HOSTNAME",
        "DYNDNS_USERNAME",
        "DYNDNS_PASSWORD",
        "UNIFI_API_USERNAME",
        "UNIFI_API_PASSWORD"
    ]
}

# Suppress the InsecureRequestWarning for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Seconds to wait for a server to accept a connection, and then to answer
CONNECT_TIMEOUT = 3
READ_TIMEOUT = 15

_ipv6_checked = False


def ipv6_reaches(host: str, port: int = 443) -> bool:
    """
    Checks whether this host can open a connection to `host` over IPv6.

    Returns True when the host has no IPv6 address (nothing to fall back from), so only a
    WAN with an IPv6 address and route that doesn't actually get through returns False.
    """
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_STREAM)
    except socket.gaierror:
        return True
    family, sock_type, proto, _, address = infos[0]
    try:
        with socket.socket(family, sock_type, proto) as sock:
            sock.settimeout(CONNECT_TIMEOUT)
            sock.connect(address)
        return True
    except OSError:
        return False


def http_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    Sends an outbound request, using IPv4 only for the rest of the run if IPv6 doesn't reach the server.

    Hostnames such as api.cloudflare.com resolve to several IPv6 addresses, which are tried before
    IPv4. When the WAN has IPv6 but it doesn't route, each one has to time out first, which made
    runs take longer than the scheduler allows. A single quick IPv6 check up front avoids that.
    """
    global _ipv6_checked
    if not _ipv6_checked:
        _ipv6_checked = True
        host = urllib3.util.parse_url(url).host
        if host and not ipv6_reaches(host):
            print(f"Could not reach {host} over IPv6. Using IPv4 only.")
            urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET
    kwargs.setdefault("timeout", (CONNECT_TIMEOUT, READ_TIMEOUT))
    return requests.request(method, url, **kwargs)


class UnifiAPIClient:
    """
    A client to interact with the UniFi Network Application API using username and password.
    Designed for UniFi OS-based consoles like the Cloud Gateway Ultra.
    """

    def __init__(self, controller_url: str, site_name: str, username: str, password: str, debug: bool = False):
        """
        Initializes the UniFi API client with all required connection details and credentials.

        Args:
            controller_url (str): The base URL of your UniFi controller (e.g., "https://192.168.0.1").
            site_name (str): The name of the UniFi site to connect to (default: "default").
            username (str): Your UniFi OS username.
            password (str): Your UniFi OS password.
            debug (bool): If True, enables verbose logging for troubleshooting (default: False).
        """
        self.controller_url = controller_url.rstrip('/')
        self.site_name = site_name
        self.username = username
        self.password = password
        self.debug = debug
        self.session = requests.Session()
        self.session.verify = False  # UniFi controllers often use self-signed certs
        self.logged_in = False  # Track login status

        # Base path for UniFi OS API endpoints
        self.api_auth_path = "/api/auth"
        self.network_api_path = f"/proxy/network/api/s/{site_name}"

    def login(self):
        """
        Logs into the UniFi controller and establishes a session.
        This method should be called once to establish the session.

        Returns:
            bool: True if login is successful, False otherwise.
        """

        if self.logged_in:
            print("Already logged in. Skipping re-login.")
            return True

        login_url = f"{self.controller_url}{self.api_auth_path}/login"
        payload = {
            "username": self.username,
            "password": self.password
        }
        headers = {
            "Content-Type": "application/json"
        }

        print(f"Attempting to log in to {login_url}...")
        try:
            response = self.session.post(login_url, data=json.dumps(payload), headers=headers, timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

            if response.status_code == 200:
                print("Login successful.")
                self.logged_in = True
                return True
            else:
                print(f"Login failed. Status code: {response.status_code}, Response: {response.text}")
                self.logged_in = False
                return False
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error during login: {e}")
            print(f"Response content: {e.response.text}")
            self.logged_in = False
            return False
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error during login: {e}")
            print("Please check the controller URL and ensure the UniFi controller is reachable.")
            self.logged_in = False
            return False
        except requests.exceptions.Timeout:
            print("Login request timed out. The controller might be slow or unreachable.")
            self.logged_in = False
            return False
        except Exception as e:
            print(f"An unexpected error occurred during login: {e}")
            self.logged_in = False
            return False

    def logout(self):
        """
        Logs out from the UniFi controller and closes the session.
        This method should be called when you are done with the client.
        """

        if not self.logged_in:
            print("Not logged in. Skipping logout.")
            return

        logout_url = f"{self.controller_url}{self.api_auth_path}/logout"
        print(f"Attempting to log out from {logout_url}...")
        try:
            self.session.post(logout_url, timeout=5)
            print("Logout successful.")
        except Exception as e:
            print(f"Error during logout: {e}")
        finally:
            self.session.close()
            self.logged_in = False

    @staticmethod
    def wan_ipv4_address(wan_data: dict | None) -> str | None:
        """
        Returns the IPv4 address on the WAN interface from get_wan() data. Behind CGNAT or an
        upstream router this is not the public address, but it is used to send the public
        address lookup out of that WAN.
        """
        address = (wan_data or {}).get('ip')
        if not address:
            print("Could not find a WAN IPv4 address for this WAN.")
        return address or None

    @staticmethod
    def wan_ipv6_address(wan_data: dict | None) -> str | None:
        """
        Picks the first non-link-local IPv6 address from get_wan() data.
        """
        for ipv6 in (wan_data or {}).get('ipv6') or []:
            if not ipv6.startswith('fe80:'):
                print(f"Found WAN IPv6 address: {ipv6}")
                return ipv6
        print("Could not find a WAN IPv6 address for this WAN.")
        return None

    def get_wan_ipv6_address(self, wan: str = "wan1") -> str | None:
        """
        Retrieves the WAN IPv6 address (e.g., "2001:db8::1") of the given WAN, or None.
        """
        return self.wan_ipv6_address(self.get_wan(wan))

    def get_wan(self, wan: str = "wan1") -> dict | None:
        """
        Retrieves one WAN's details from the gateway using the authenticated session.

        This method queries the '/stat/device' endpoint to get detailed information
        about all devices, identifies the gateway, and returns the data for the requested WAN.

        Args:
            wan (str): Which WAN to return: 'wan1' (primary), 'wan2', ...

        Returns:
            dict or None: The WAN data (including 'ip' and 'ipv6') if found, otherwise None.
        """

        if not self.logged_in:
            print("Not logged in. Please call login() first.")
            return None

        device_url = f"{self.controller_url}{self.network_api_path}/stat/device"
        headers = {
            "Content-Type": "application/json"
            # No X-API-Key header needed when using session-based authentication
        }

        print(f"Attempting to fetch {wan} details from {device_url}...")
        try:
            response = self.session.get(device_url, headers=headers, timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
            data = response.json()
            if self.debug:
                print("[DEBUG] UniFi API Response Data:")
                print(json.dumps(data, indent=2, sort_keys=True))

            found_gateway = None
            if data and 'data' in data and isinstance(data['data'], list):
                for device in data['data']:
                    device_type = device.get('type')
                    device_model = device.get('model', '').upper()  # Convert to uppercase for consistent comparison

                    # Any UniFi OS console (UDR7, UCG Ultra, ...) reports type 'udm', including ones used only
                    # as access points (e.g. a UX7 in AP mode), so also require WAN data; optionally pin a model
                    wanted_model = os.getenv("UNIFI_GATEWAY_MODEL", "").upper()
                    if (device_type == 'udm' and isinstance(device.get(wan), dict)
                            and (not wanted_model or device_model == wanted_model)):
                        found_gateway = device
                        print(f"Found potential gateway device: {device.get('name', device.get('mac'))} "
                              f"(Type: {device_type}, Model: {device_model})")
                        break

            if found_gateway:
                return found_gateway[wan]
            else:
                print(f"UniFi gateway with {wan} (or specified model) not found among devices in the API response.")
                # Print full data for debugging if no gateway found at all
                # if data and 'data' in data:
                #    print("Full device data for debugging:", json.dumps(data['data'], indent=2))
                return None

        except requests.exceptions.HTTPError as e:
            print(f"HTTP error fetching {wan} details: {e}")
            print(f"Response content: {e.response.text}")
            # If an authentication token expires, try to log in again
            if e.response.status_code == 401:
                print("Authentication failed (401). Session might have expired. Attempting to re-login.")
                self.logged_in = False  # Mark as not logged in
                if self.login():  # Try to log in again
                    return self.get_wan(wan)  # Retry the request
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error fetching {wan} details: {e}")
            print("Please check the controller URL and ensure the UniFi controller is reachable.")
            return None
        except requests.exceptions.Timeout:
            print(f"{wan} details request timed out.")
            return None
        except json.JSONDecodeError:
            print("Failed to decode JSON response from UniFi controller. Response might not be valid JSON.")
            return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return None


class CloudflareDNSClient:
    """
    A client for managing DNS records in Cloudflare via the API.
    """

    def __init__(self, api_token: str, zone_id: str):
        """
        Initializes the client with the Cloudflare API token and Zone ID.

        Args:
            api_token (str): Your Cloudflare API token with Zone > DNS > Edit permissions.
            zone_id (str): The ID of the DNS zone (domain) you are managing.
        """
        self.api_token = api_token
        self.zone_id = zone_id
        self.api_url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

    def get_record_id(self, record_name: str, record_type: str = "AAAA") -> tuple[str, str] | tuple[None, None]:
        """
        Finds the ID and content of a specific DNS record.

        Args:
            record_name (str): The name of the record (e.g., 'example.com' or 'www').
            record_type (str): The type of the record (e.g., 'A', 'AAAA', 'CNAME').

        Returns:
            tuple[str, str] | tuple[None, None]: A tuple containing the record ID and its content (IP address) if found,
            otherwise (None, None).
        """
        try:
            record = self._find_record(record_name, record_type)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching record ID: {e}")
            return None, None

        if record is None:
            print(f"Could not find {record_type} record with name: {record_name}")
            return None, None
        return record["id"], record["content"]

    def _find_record(self, record_name: str, record_type: str) -> dict | None:
        """
        Looks up a DNS record, distinguishing "not found" (returns None) from a failed
        lookup (raises), so callers never create a duplicate record after an API error.
        """
        params = {
            "type": record_type,
            "name": record_name
        }
        response = http_request("GET", self.api_url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()

        if not data["success"]:
            raise requests.exceptions.RequestException(f"Cloudflare API errors: {data['errors']}")
        if not data["result"]:
            return None

        record = data["result"][0]
        print(f"Found record ID: {record['id']} with current IP: {record['content']}")
        return record

    def create_record(self, record_name: str, record_type: str, content: str, proxied: bool = False) -> bool:
        """
        Creates a new DNS record.

        Args:
            record_name (str): The name of the record to create (e.g., 'home.example.com').
            record_type (str): The type of the record (e.g., 'A', 'AAAA').
            content (str): The IP address for the record.
            proxied (bool): Whether to enable Cloudflare's proxy (orange cloud). Defaults to False.

        Returns:
            bool: True if the record was created, False otherwise.
        """
        payload = {
            "type": record_type,
            "name": record_name,
            "content": content,
            "ttl": 1,  # automatic
            "proxied": proxied
        }

        try:
            response = http_request("POST", self.api_url, headers=self.headers, data=json.dumps(payload))
            response.raise_for_status()
            data = response.json()

            if data["success"]:
                print(f"Created {record_type} record '{record_name}' with '{content}'.")
                return True
            else:
                print(f"Failed to create {record_type} record. Errors: {data['errors']}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Error creating record: {e}")
            return False

    def upsert_record(self, record_name: str, record_type: str, new_ip_address: str, proxied: bool = False) -> bool:
        """
        Points an A/AAAA record at new_ip_address, creating the record if it does not exist.
        Existing records are patched so their proxy status, TTL and comment are kept.

        Args:
            record_name (str): The name of the record (e.g., 'home.example.com').
            record_type (str): 'A' or 'AAAA'.
            new_ip_address (str): The IP address the record should point to.
            proxied (bool): Proxy status for a newly created record. Defaults to False.

        Returns:
            bool: True if the record is now up to date, False otherwise.
        """
        try:
            record = self._find_record(record_name, record_type)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching record ID: {e}")
            return False

        if record is None:
            print(f"No {record_type} record named '{record_name}' yet. Creating it.")
            return self.create_record(record_name, record_type, new_ip_address, proxied)

        # Check if the IP has changed before updating
        if record["content"] == new_ip_address:
            print(f"{record_type} record already points to {new_ip_address}. No update needed.")
            return True

        update_url = f"{self.api_url}/{record['id']}"

        try:
            response = http_request("PATCH", update_url, headers=self.headers,
                                    data=json.dumps({"content": new_ip_address}))
            response.raise_for_status()
            data = response.json()

            if data["success"]:
                print(f"Successfully updated {record_type} record '{record_name}' to '{new_ip_address}'.")
                return True
            else:
                print(f"Failed to update {record_type} record. Errors: {data['errors']}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Error updating record: {e}")
            return False

    def update_a_record(self, record_name: str, new_ipv4_address: str, proxied: bool = False) -> bool:
        """
        Updates (or creates) an A record with a new IPv4 address.
        """
        return self.upsert_record(record_name, "A", new_ipv4_address, proxied)

    def update_aaaa_record(self, record_name: str, new_ipv6_address: str, proxied: bool = False) -> bool:
        """
        Updates (or creates) an AAAA record with a new IPv6 address.
        """
        return self.upsert_record(record_name, "AAAA", new_ipv6_address, proxied)


class HurricaneElectricDNSClient:
    """
    A client for updating DNS records with Hurricane Electric's Dynamic DNS service.
    """
    HE_BASE_URL = "https://dyn.dns.he.net/nic/update"

    def __init__(self, hostname: str, password: str):
        """
        Initializes the client with the hostname and password for the DNS update.

        Args:
            hostname (str): The hostname to update (e.g., "dyn.example.com").
            password (str): The password for the DNS update.
        """
        self.hostname = hostname
        self.password = password

    def update_dns(self, ip: str) -> bool:
        """
        Updates the DNS record with the specified IP address.

        Args:
            ip (str): The IP address to update.

        Returns:
            bool: True if the update was successful, False otherwise.
        """
        payload = {
            "hostname": self.hostname,
            "password": self.password,
            "myip": ip
        }

        print(f"Attempting to update DNS for hostname: {self.hostname}")
        print(f"Using URL: {self.HE_BASE_URL}")

        try:
            response = http_request("POST", self.HE_BASE_URL, data=payload)
            response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)

            print(f"DNS Update Successful! Status Code: {response.status_code}")
            print(f"Response Body: {response.text}")
            return True

        except requests.exceptions.HTTPError as errh:
            print(f"Http Error during DNS update: {errh}")
        except requests.exceptions.ConnectionError as errc:
            print(f"Error Connecting during DNS update: {errc}")
        except requests.exceptions.Timeout as errt:
            print(f"Timeout Error during DNS update: {errt}")
        except requests.exceptions.RequestException as err:
            print(f"An unexpected error occurred during DNS update: {err}")

        return False


class DynDNSClient:
    """
    A client for updating DNS records using the standard DynDNS v2 API.
    Optimized for modern providers like IPv64.net.
    """

    def __init__(self, hostname: str, username: str, password: str, update_url: str):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.update_url = update_url

    def update_dns(self, ipv4: str | None = None, ipv6: str | None = None) -> bool:
        """
        Updates the DNS record with the specified IPv4 and/or IPv6 addresses.

        Args:
            ipv4 (str | None): The IPv4 address to update.
            ipv6 (str | None): The IPv6 address to update.

        Returns:
            bool: True if the update was successful, False otherwise.
        """
        if not ipv4 and not ipv6:
            print("Error: You must provide at least one IP address (IPv4 | IPv6) to update.")
            return False

        payload = {
            "hostname": self.hostname,
            "key": self.password,
        }

        if ipv4:
            payload["myip"] = ipv4
        if ipv6:
            payload["myipv6"] = ipv6

        headers = {
            "User-Agent": "Unifi-IPv6-DynDNS-Updater/1.0",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        print(f"Attempting to update DNS for hostname: {self.hostname}")
        print(f"Using URL: {self.update_url}")

        try:
            response = http_request(
                "POST",
                self.update_url,
                data=payload,
                auth=(self.username, self.password),  # Dual-method auth for maximum compatibility
                headers=headers
            )
            response.raise_for_status()
            response_text = response.text.strip()

            try:
                data = response.json()
                # Check for "success" status or the standard "good"/"nochg" keywords
                status = data.get("status")
                info = data.get("info")

                if status == "success" or info in ["good", "nochg"]:
                    print(f"DNS Update Successful: {info if info else status}")
                    return True
                else:
                    print(f"Warning: Provider returned a failure response: {data}")
                    return False

            # Fallback to plain text
            except ValueError:
                if response_text.startswith("good") or response_text.startswith("nochg"):
                    print(f"DNS Update Successful: {response_text}")
                    return True
                else:
                    print(f"Warning: Provider returned an unexpected response: {response_text}")
                    return False

        except requests.exceptions.HTTPError as errh:
            print(f"Http Error during DNS update: {errh}")
        except requests.exceptions.ConnectionError as errc:
            print(f"Error Connecting during DNS update: {errc}")
        except requests.exceptions.Timeout as errt:
            print(f"Timeout Error during DNS update: {errt}")
        except requests.exceptions.RequestException as err:
            print(f"An unexpected error occurred during DNS update: {err}")

        return False


class SourceAddressAdapter(requests.adapters.HTTPAdapter):
    """
    Sends requests from a specific local address. On a multi-WAN gateway this picks the WAN,
    since UniFi OS routes traffic by source address.
    """

    def __init__(self, source_address: str, **kwargs):
        self.source_address = source_address
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["source_address"] = (self.source_address, 0)
        super().init_poolmanager(*args, **kwargs)


def get_public_ipv4(source_address: str | None = None) -> str | None:
    """
    Asks Cloudflare which IPv4 address this host reaches the internet from.

    The UniFi API only knows the WAN interface address, which behind CGNAT
    (100.64.0.0/10) or an upstream router is not reachable from the internet.
    Connecting to 1.1.1.1 by IP forces the lookup over IPv4.

    Args:
        source_address (str): Optional local address to send the lookup from (selects the WAN).

    Returns:
        str or None: The public IPv4 address, or None if it could not be determined
        or is not a globally routable address.
    """
    session = requests.Session()
    if source_address:
        session.mount("https://", SourceAddressAdapter(source_address))
    try:
        response = session.get("https://1.1.1.1/cdn-cgi/trace", timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error looking up public IPv4 address: {e}")
        return None

    for line in response.text.splitlines():
        if line.startswith("ip="):
            try:
                address = ipaddress.ip_address(line[3:].strip())
            except ValueError:
                break
            if address.version == 4 and address.is_global:
                print(f"Found public IPv4 address: {address}")
                return str(address)
            print(f"Refusing to publish {address}: not a public IPv4 address.")
            return None

    print("Could not parse public IPv4 address from Cloudflare trace.")
    return None


def main():
    parser = argparse.ArgumentParser(description="UniFi IPv6 Dynamic DNS Updater")
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        default=os.getenv("DEBUG", "false").lower() == "true",
        help="Enable verbose debug logging"
    )
    args = parser.parse_args()

    # Determine the DNS provider
    dns_provider = os.getenv("DNS_PROVIDER")
    if dns_provider not in REQUIRED_ENV_VARIABLES:
        raise EnvironmentError(
            "DNS_PROVIDER environment variable is not set or is invalid. Use 'HE', 'Cloudflare', or 'DynDNS'.")

    # Validate required environment variables for the selected provider
    required_vars = REQUIRED_ENV_VARIABLES[dns_provider]
    env_values = {}
    for var_name in required_vars:
        value = os.getenv(var_name)
        if value is None or value == "":
            raise EnvironmentError(
                f"Required environment variable '{var_name}' for {dns_provider} is not set or is empty.")
        env_values[var_name] = value

    # Get UniFi controller details, or otherwise assume the defaults
    unifi_controller_url = os.getenv("UNIFI_CONTROLLER_URL", "https://192.168.0.1")
    unifi_site_name = os.getenv("UNIFI_SITE_NAME", "default")

    # Which WAN to publish, and which record types (IPv6-only toggle is Cloudflare only)
    unifi_wan = os.getenv("UNIFI_WAN", "wan1")
    update_ipv6 = dns_provider != "Cloudflare" or os.getenv("CLOUDFLARE_UPDATE_IPV6", "true").lower() == "true"
    update_ipv4 = dns_provider == "Cloudflare" and os.getenv("CLOUDFLARE_UPDATE_IPV4", "false").lower() == "true"
    if not (update_ipv6 or update_ipv4):
        raise EnvironmentError("Both CLOUDFLARE_UPDATE_IPV6 and CLOUDFLARE_UPDATE_IPV4 are off. Nothing to do.")

    # Get the current IP addresses
    current_ip = None
    wan_ipv4 = None
    unifi_api_client = UnifiAPIClient(
        controller_url=unifi_controller_url,
        site_name=unifi_site_name,
        username=env_values["UNIFI_API_USERNAME"],
        password=env_values["UNIFI_API_PASSWORD"],
        debug=args.debug
    )

    if unifi_api_client.login():
        wan_data = unifi_api_client.get_wan(unifi_wan)
        unifi_api_client.logout()
        if update_ipv6:
            current_ip = unifi_api_client.wan_ipv6_address(wan_data)
        if update_ipv4:
            wan_ipv4 = unifi_api_client.wan_ipv4_address(wan_data)

    # IPv6 and IPv4 are handled independently, so stop only if neither is available
    if not (current_ip or wan_ipv4):
        print("Could not retrieve current IP address. Exiting.")
        sys.exit(1)

    # Initialize and use the correct DNS client based on the provider
    if dns_provider == "HE":
        he_client = HurricaneElectricDNSClient(
            hostname=env_values["HE_HOSTNAME"],
            password=env_values["HE_PASSWORD"]
        )
        ok = he_client.update_dns(ip=current_ip)

    elif dns_provider == "Cloudflare":
        cf_client = CloudflareDNSClient(
            api_token=env_values["CLOUDFLARE_API_TOKEN"],
            zone_id=env_values["CLOUDFLARE_ZONE_ID"]
        )
        ok = True
        if update_ipv6:
            ok = current_ip is not None and cf_client.update_aaaa_record(
                record_name=env_values["CLOUDFLARE_RECORD_NAME"],
                new_ipv6_address=current_ip
            )

        # Optionally keep the A record on the same name pointed at this WAN's public IPv4 address
        if update_ipv4:
            public_ipv4 = get_public_ipv4(source_address=wan_ipv4) if wan_ipv4 else None
            ipv4_ok = public_ipv4 is not None and cf_client.update_a_record(
                record_name=env_values["CLOUDFLARE_RECORD_NAME"],
                new_ipv4_address=public_ipv4
            )
            ok = ok and ipv4_ok

    elif dns_provider == "DynDNS":
        dyndns_client = DynDNSClient(
            hostname=env_values["DYNDNS_HOSTNAME"],
            username=env_values["DYNDNS_USERNAME"],
            password=env_values["DYNDNS_PASSWORD"],
            update_url=env_values["DYNDNS_UPDATE_URL"]
        )
        ok = dyndns_client.update_dns(ipv6=current_ip)

    else:
        print(f"Unknown DNS provider: {dns_provider}")
        ok = False

    # Non-zero exit so schedulers (cron, systemd) can see failed runs
    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
