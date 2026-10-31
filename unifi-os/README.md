# Running on the UniFi OS Console

Runs the updater directly on the console, so no other machine needs to be on. Tested on a UniFi Dream Router 7
(UniFi OS 5.1.34, Python 3.9). It uses the console's own `python3` and `requests`, so nothing extra is installed.
Cloudflare only.

## Before you start

1. **Turn on SSH:** UniFi → Settings → Control Plane → Console → SSH, and set a password.
2. **Create a local user for the script:** Settings → Admins & Users, local access only, **View Only** role.
3. **Cloudflare:** an API token with Zone > DNS > Edit for your zone, and the zone ID (zone Overview page, right
   sidebar). The record doesn't need to exist; it's created on the first run.

## Install

From your computer, in this repository:

```bash
ssh root@<gateway-ip> mkdir -p /data/unifi-ddns6
scp dynamic_dns.py unifi-os/install.sh unifi-os/set-secrets.sh root@<gateway-ip>:/data/unifi-ddns6/
```

Then on the console (`ssh root@<gateway-ip>`):

```bash
/data/unifi-ddns6/install.sh       # creates and starts the systemd timer (every 2 minutes)
/data/unifi-ddns6/set-secrets.sh   # prompts for credentials, writes .env, runs a test update
```

`set-secrets.sh` asks for the UniFi user, record name, zone ID, API token, and whether to manage the IPv4 A record
too. Passwords and the token aren't echoed. They're saved to `/data/unifi-ddns6/.env`, readable only by root. Run it
again any time to change them.

A successful test ends with `Created …`, `Successfully updated …` or `… No update needed.`

If you said yes to IPv4, remove the same hostname from UniFi's built-in Dynamic DNS (Settings → Internet → your WAN
→ Dynamic DNS). Otherwise it will keep setting the A record back to the WAN port's address, which behind CGNAT isn't
reachable.

## How it runs

* Starts 2 minutes after boot, then every 2 minutes.
* Uses the local API at `https://127.0.0.1`, so it keeps working if the console's LAN IP changes.
* Only writes to Cloudflare when an address has actually changed.

## Checking on it

```bash
systemctl is-active unifi-ddns6.timer        # "active" means it's scheduled
systemctl list-timers unifi-ddns6.timer      # last and next run
journalctl -u unifi-ddns6 -n 20              # output of recent runs
systemctl start unifi-ddns6.service          # run it now
```

## After a firmware update

Everything lives in `/data`, which survives firmware updates. The two systemd units in `/etc/systemd/system` may not.
If `systemctl is-active unifi-ddns6.timer` doesn't print `active`, put them back with:

```bash
/data/unifi-ddns6/install.sh
```

Re-running it when the timer is already installed is harmless.

## Files

| Path                               | Purpose                                            |
|:-----------------------------------|:---------------------------------------------------|
| `/data/unifi-ddns6/dynamic_dns.py` | The updater                                        |
| `/data/unifi-ddns6/.env`           | Settings and credentials (mode 600)                |
| `/data/unifi-ddns6/install.sh`     | Writes and enables the systemd service and timer   |
| `/data/unifi-ddns6/set-secrets.sh` | Prompts for settings and writes `.env`             |

## Uninstall

```bash
systemctl disable --now unifi-ddns6.timer
rm /etc/systemd/system/unifi-ddns6.{service,timer}
systemctl daemon-reload
rm -r /data/unifi-ddns6
```
