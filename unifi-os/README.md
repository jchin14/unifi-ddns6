# Running on the UniFi OS Console

Runs the updater directly on the console, so no other machine needs to be on. Tested on a UniFi Dream Router 7
(UniFi OS 5.1.34, Python 3.9) with two WANs. It uses the console's own `python3` and `requests`, so nothing extra is
installed. Cloudflare only.

Each hostname gets its own settings file (`/data/unifi-ddns6/<name>.env`) and its own timer
(`unifi-ddns6@<name>.timer`), so you can, for example, publish `home` from the primary WAN and `secondary` from the
secondary WAN.

## Before you start

1. **Turn on SSH:** UniFi → Settings → Control Plane → Console → SSH, and set a password.
2. **Create a local user for the script:** Settings → Admins & Users, local access only, **View Only** role.
3. **Cloudflare:** an API token with Zone > DNS > Edit for your zone, and the zone ID (zone Overview page, right
   sidebar). Records don't need to exist; they're created on the first run.

## Install

From your computer, in this repository:

```bash
ssh root@<gateway-ip> mkdir -p /data/unifi-ddns6
scp dynamic_dns.py unifi-os/install.sh unifi-os/set-secrets.sh root@<gateway-ip>:/data/unifi-ddns6/
```

Then on the console (`ssh root@<gateway-ip>`):

```bash
/data/unifi-ddns6/install.sh               # installs the systemd units
/data/unifi-ddns6/set-secrets.sh home      # adds a hostname called "home", enables its timer, runs a test
/data/unifi-ddns6/set-secrets.sh secondary # optional: another hostname, e.g. for a second WAN
```

`set-secrets.sh <name>` asks for:

| Prompt                         | Notes                                                                       |
|:-------------------------------|:----------------------------------------------------------------------------|
| Reuse credentials from …?      | Only if another hostname is already set up. Skips the next four questions. |
| UniFi username / password      | The View Only user. The password isn't shown as you type.                  |
| Cloudflare zone ID / API token | The token isn't shown as you type.                                         |
| Record name                    | e.g. `home.example.com`                                                     |
| Which WAN                      | `wan1` (primary, default) or `wan2` (secondary)                             |
| IPv6 (AAAA)?                   | Default yes. Answer no for a WAN without IPv6.                              |
| Public IPv4 (A)?               | Default no.                                                                 |

Settings are saved to `/data/unifi-ddns6/<name>.env`, readable only by root. Run it again with the same name any time
to change them.

A successful test ends with `Created …`, `Successfully updated …` or `… No update needed.`

If you enable IPv4, remove the same hostname from UniFi's built-in Dynamic DNS (Settings → Internet → your WAN →
Dynamic DNS). Otherwise it will keep setting the A record back to the WAN port's address, which behind CGNAT or
another router isn't reachable.

## How it runs

* Starts 2 minutes after boot, then every 2 minutes, for each hostname.
* Uses the local API at `https://127.0.0.1`, so it keeps working if the console's LAN IP changes.
* The public IPv4 lookup goes out of the chosen WAN, so each record keeps its own WAN's address during failover.
* Only writes to Cloudflare when an address has actually changed.

## Checking on it

```bash
systemctl list-timers 'unifi-ddns6@*'        # one line per hostname: last and next run
journalctl -u 'unifi-ddns6@*' -n 30          # output of recent runs
journalctl -u unifi-ddns6@home -n 20         # just one hostname
systemctl start unifi-ddns6@home.service     # run one now
```

## After a firmware update

Everything lives in `/data`, which survives firmware updates. The systemd units in `/etc/systemd/system` may not. If
`systemctl list-timers 'unifi-ddns6@*'` shows nothing, put them back with:

```bash
/data/unifi-ddns6/install.sh
```

It re-enables a timer for every `.env` file it finds. Re-running it when everything is already installed is harmless.

## Upgrading from the single-hostname setup

Earlier versions used one `unifi-ddns6.timer` and `/data/unifi-ddns6/.env`. Copy the new files over and run
`install.sh`: it removes the old timer, renames `.env` to `home.env` and enables `unifi-ddns6@home.timer`.

## Files

| Path                               | Purpose                                                  |
|:-----------------------------------|:---------------------------------------------------------|
| `/data/unifi-ddns6/dynamic_dns.py` | The updater                                              |
| `/data/unifi-ddns6/<name>.env`     | Settings and credentials for one hostname (mode 600)     |
| `/data/unifi-ddns6/install.sh`     | Installs the systemd units and enables a timer per file  |
| `/data/unifi-ddns6/set-secrets.sh` | Prompts for one hostname's settings and writes its file  |

## Removing a hostname

```bash
systemctl disable --now unifi-ddns6@secondary.timer
rm /data/unifi-ddns6/secondary.env
```

## Uninstall

```bash
for f in /data/unifi-ddns6/*.env; do systemctl disable --now "unifi-ddns6@$(basename "$f" .env).timer"; done
rm /etc/systemd/system/unifi-ddns6@.{service,timer}
systemctl daemon-reload
rm -r /data/unifi-ddns6
```
