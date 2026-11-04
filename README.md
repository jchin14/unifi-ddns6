# UniFi IPv6 Dynamic DNS Updater

Keeps a DNS record pointed at your UniFi gateway's current WAN IPv6 address, so services stay reachable when your ISP
changes your prefix. UniFi's built-in Dynamic DNS doesn't support IPv6.

- **IPv6:** reads the WAN address from your UniFi console and updates the AAAA record.
- **IPv4 (Cloudflare):** optionally updates the A record with the address the internet actually sees, so it stays
  correct behind CGNAT or an upstream router.
- **Runs once and exits:** schedule it with cron or a systemd timer, on any machine that can reach the console or
  [on the console itself](#running-on-the-unifi-os-console).

## Supported Providers

* Hurricane Electric (HE)
* Cloudflare
* DynDNS-compatible (Dyn, IPv64.net, No-IP, ...)

## Tested Devices

| Device                         | Model code | UniFi OS | Notes                                    |
|:-------------------------------|:-----------|:---------|:-----------------------------------------|
| UniFi Cloud Gateway Ultra      | UDRULT     |          | Original target                          |
| UniFi Dream Router 7           | UDMA67A    | 5.1.34   | Running on the console itself, Python 3.9 |

The script uses the first UniFi OS console (device type `udm`) it finds, so other consoles should work too. If you have
more than one, set `UNIFI_GATEWAY_MODEL`. Please open an issue / pull request to add more devices to the list, and
include the anonymized output of the script in debug mode (see [Debug Mode](#debug-mode)).

## Requirements

* Python 3.9 or newer
* [`requests`](https://pypi.org/project/requests/) (`pip install -r requirements.txt`). UniFi OS consoles already
  have it.

## Getting Started

Configure the script with environment variables for UniFi and your DNS provider.

1. **UniFi Configuration**

   All configurations require the following UniFi-related environment variables:

| Variable             | Description                                                                                                             |
|:---------------------|:------------------------------------------------------------------------------------------------------------------------|
| UNIFI_CONTROLLER_URL | The URL of your UniFi controller (e.g., https://192.168.0.1).<br/> If not provided, it defaults to https://192.168.0.1. |
| UNIFI_GATEWAY_MODEL  | Optional. Only match a gateway with this model code (e.g. UDRULT). If not provided, the first console with a WAN is used. |
| UNIFI_SITE_NAME      | The name of your UniFi site (e.g., default). If not provided, it defaults to default.                                   |
| UNIFI_WAN            | Optional. Which WAN to publish: `wan1` (primary, default), `wan2`, ...                                                  |
| UNIFI_API_USERNAME   | A local UniFi OS user. The **View Only** role is enough.                                                                |
| UNIFI_API_PASSWORD   | Your UniFi OS password.                                                                                                 |

2. **Provider-Specific Configuration**

   Set the DNS_PROVIDER environment variable to `HE`, `Cloudflare` or `DynDNS`, and then configure the required
   variables for your provider.

### Hurricane Electric (HE)

| Variable    | Description                                              |
|:------------|:---------------------------------------------------------|
| HE_HOSTNAME | The hostname of your DNS record (e.g., dyn.example.com). |
| HE_PASSWORD | The password for the DNS update.                         |

Example:

```bash
export DNS_PROVIDER=HE
export HE_HOSTNAME="dyn.example.com"
export HE_PASSWORD="your-he-password"
export UNIFI_API_USERNAME="your-unifi-username"
export UNIFI_API_PASSWORD="your-unifi-password"
```

### Cloudflare

| Variable               | Description                                                                                       |
|:-----------------------|:--------------------------------------------------------------------------------------------------|
| CLOUDFLARE_API_TOKEN   | A Cloudflare API token with Zone > DNS > Edit permissions for your zone.                          |
| CLOUDFLARE_ZONE_ID     | The ID of the DNS zone you are managing (zone Overview page, right sidebar).                      |
| CLOUDFLARE_RECORD_NAME | The name of the AAAA record to update (e.g., ddns.example.com).                                   |
| CLOUDFLARE_UPDATE_IPV4 | Optional. Set to `true` to also keep the A record of the same name pointed at your public IPv4.   |
| CLOUDFLARE_UPDATE_IPV6 | Optional. Defaults to `true`. Set to `false` for an IPv4-only record, e.g. a WAN without IPv6.    |

Example:

```bash
export DNS_PROVIDER=Cloudflare
export CLOUDFLARE_API_TOKEN="your-cloudflare-api-token"
export CLOUDFLARE_ZONE_ID="your-cloudflare-zone-id"
export CLOUDFLARE_RECORD_NAME="ddns.example.com"
export CLOUDFLARE_UPDATE_IPV4=true   # optional
export UNIFI_API_USERNAME="your-unifi-username"
export UNIFI_API_PASSWORD="your-unifi-password"
```

How records are handled:

* **Missing:** created as DNS only (grey cloud) with automatic TTL.
* **Unchanged:** left alone. Each run is a single lookup, so running every couple of minutes is fine.
* **Changed:** only the address is updated. The record's proxy status, TTL and comment are kept.
* **Lookup fails** (bad token, wrong zone, outage): nothing is written, so an error never creates a duplicate record.

**Public IPv4:** UniFi only knows the address on its WAN port. Behind CGNAT (`100.64.0.0/10`) or another router, that
address isn't reachable from the internet. With `CLOUDFLARE_UPDATE_IPV4=true` the script asks Cloudflare
(`https://1.1.1.1/cdn-cgi/trace`) which address you connect from and refuses to publish anything that isn't a public
IPv4 address. If you enable this, remove the same hostname from UniFi's built-in Dynamic DNS, or the two will keep
overwriting each other.

**Multiple WANs:** run the script once per hostname with a different `UNIFI_WAN`. The public IPv4 lookup is sent from
that WAN's own interface address, so each record gets its own WAN's address and doesn't follow failover. IPv6
and IPv4 are handled independently: if one can't be found, the other is still updated (and the run exits `1`).
For example, an IPv4-only record for a secondary WAN:

```bash
export UNIFI_WAN=wan2
export CLOUDFLARE_RECORD_NAME="secondary.example.com"
export CLOUDFLARE_UPDATE_IPV4=true
export CLOUDFLARE_UPDATE_IPV6=false
```

### DynDNS (Dyn | IPv64.net | No-IP | Others )

| Variable          | Description                                                              |
|:------------------|:-------------------------------------------------------------------------|
| DYNDNS_UPDATE_URL | The API endpoint for your provider (e.g., https://ipv64.net/nic/update). |
| DYNDNS_HOSTNAME   | The hostname to update.                                                  |
| DYNDNS_USERNAME   | Your DynDNS service username (often the same as the hostname).           |
| DYNDNS_PASSWORD   | Your DynDNS service password / API token.                                |

Example:

```bash
export DNS_PROVIDER=DynDNS
export DYNDNS_UPDATE_URL="https://ipv64.net/nic/update"
export DYNDNS_HOSTNAME="example.ipv64.net"
export DYNDNS_USERNAME="your-dyndns-username"
export DYNDNS_PASSWORD="your-dyndns-api-token"
export UNIFI_API_USERNAME="your-unifi-username"
export UNIFI_API_PASSWORD="your-unifi-password"
```

## Running on the UniFi OS Console

The [`unifi-os/`](unifi-os/) folder installs the script on the console itself (Cloudflare only): one systemd timer
per hostname that runs every 4 minutes, plus a helper that prompts for settings and stores them in a root-only file. See
[unifi-os/README.md](unifi-os/README.md).

## Exit Status

The script exits `0` when the DNS record is up to date and `1` if it couldn't get the IP address or update the record,
so cron or systemd can flag failed runs.

## Debug Mode

Prints the raw JSON from your UniFi controller, for troubleshooting. Enable it either way (the flag takes precedence):

-  **Environment Variable:**
    ```bash
    export DEBUG=true
    ```
-  **Command Line Flag:**
    ```bash
    python dynamic_dns.py --debug
    # or
    python dynamic_dns.py -d
    ```

## Contributing

Issues and pull requests are welcome.
