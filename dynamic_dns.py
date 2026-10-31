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
import json
import os
import sys
import requests
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

    def get_wan_ipv4_address(self):
        """
        Retrieves the WAN IPv4 address from the UniFi controller.

        This method is currently not yet implemented and serves as a placeholder.
        It will always return the loopback address.

        Returns:
            str: The IPv4 loopback address "127.0.0.1".
        """

        print("WAN IPv4 retrieval not yet implemented. Returning placeholder '127.0.0.1'.")
        return "127.0.0.1"

    def get_wan_ipv6_address(self):
        """
        Retrieves the WAN IPv6 address from the UniFi controller using the authenticated session.

        This method queries the '/stat/device' endpoint to get detailed information
        about all devices, identifies the gateway, and then extracts its WAN IPv6 address.

        Returns:
            str or None: The WAN IPv6 address (e.g., "2001:db8::1") if found, otherwise None.
        """

        if not self.logged_in:
            print("Not logged in. Please call login() first.")
            return None

        device_url = f"{self.controller_url}{self.network_api_path}/stat/device"
        headers = {
            "Content-Type": "application/json"
            # No X-API-Key header needed when using session-based authentication
        }

        print(f"Attempting to fetch WAN IPv6 address from {device_url}...")
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

                    # Any UniFi OS console (UDR7, UCG Ultra, ...) reports type 'udm'; optionally pin a model
                    wanted_model = os.getenv("UNIFI_GATEWAY_MODEL", "").upper()
                    if device_type == 'udm' and (not wanted_model or device_model == wanted_model):
                        found_gateway = device
                        print(f"Found potential gateway device: {device.get('name', device.get('mac'))} "
                              f"(Type: {device_type}, Model: {device_model})")
                        break

            if found_gateway:
                # Now search for IPv6 within the found_gateway
                if 'wan1' in found_gateway:
                    if 'ipv6' in found_gateway['wan1'] and isinstance(found_gateway['wan1']['ipv6'], list):
                        ipv6_list = found_gateway['wan1']['ipv6']
                        for ipv6 in ipv6_list:
                            if not ipv6.startswith('fe80:'):
                                print(f"Found WAN IPv6 address: {ipv6}")
                                return ipv6

                print(f"Identified gateway '{found_gateway.get('name', found_gateway.get('mac'))}' "
                      f"but could not find a WAN IPv6 address within its data.")
                # print("Consider checking the exact JSON structure of the gateway's data for IPv6 details.")
                # print("Gateway data for debugging:", json.dumps(found_gateway, indent=2))
                return None
            else:
                print("UniFi Cloud Gateway (or specified model) not found among devices in the API response.")
                # Print full data for debugging if no gateway found at all
                # if data and 'data' in data:
                #    print("Full device data for debugging:", json.dumps(data['data'], indent=2))
                return None

        except requests.exceptions.HTTPError as e:
            print(f"HTTP error fetching WAN IPv6 address: {e}")
            print(f"Response content: {e.response.text}")
            # If an authentication token expires, try to log in again
            if e.response.status_code == 401:
                print("Authentication failed (401). Session might have expired. Attempting to re-login.")
                self.logged_in = False  # Mark as not logged in
                if self.login():  # Try to log in again
                    return self.get_wan_ipv6_address()  # Retry the request
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error fetching WAN IPv6 address: {e}")
            print("Please check the controller URL and ensure the UniFi controller is reachable.")
            return None
        except requests.exceptions.Timeout:
            print("WAN IPv6 address request timed out.")
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
        response = requests.get(self.api_url, headers=self.headers, params=params, timeout=15)
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
            response = requests.post(self.api_url, headers=self.headers, data=json.dumps(payload), timeout=15)
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
            response = requests.patch(update_url, headers=self.headers,
                                      data=json.dumps({"content": new_ip_address}), timeout=15)
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
            response = requests.post(self.HE_BASE_URL, data=payload)
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
            response = requests.post(
                self.update_url,
                data=payload,
                auth=(self.username, self.password),  # Dual-method auth for maximum compatibility
                headers=headers,
                timeout=10
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

    # Get the current IP address
    current_ip = None
    unifi_api_client = UnifiAPIClient(
        controller_url=unifi_controller_url,
        site_name=unifi_site_name,
        username=env_values["UNIFI_API_USERNAME"],
        password=env_values["UNIFI_API_PASSWORD"],
        debug=args.debug
    )

    if unifi_api_client.login():
        # IPv6 address
        current_ip = unifi_api_client.get_wan_ipv6_address()
        unifi_api_client.logout()

    if not current_ip:
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
        ok = cf_client.update_aaaa_record(
            record_name=env_values["CLOUDFLARE_RECORD_NAME"],
            new_ipv6_address=current_ip
        )

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
