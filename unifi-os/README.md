# Running on the UniFi OS console itself

Tested on a UniFi Dream Router 7 (UniFi OS 5.1, Python 3.9). Uses the system
`python3` and `requests`, so nothing extra is installed. Cloudflare only.

```bash
# from your computer
ssh root@<gateway-ip> mkdir -p /data/unifi-ddns6
scp dynamic_dns.py unifi-os/install.sh unifi-os/set-secrets.sh root@<gateway-ip>:/data/unifi-ddns6/

# on the gateway
/data/unifi-ddns6/install.sh       # systemd timer, every 2 minutes
/data/unifi-ddns6/set-secrets.sh   # prompts for credentials, writes .env (600), runs a test
```

The script talks to the local API at `https://127.0.0.1` and only writes to
Cloudflare when the AAAA record differs from the current WAN IPv6 address. If
the record doesn't exist yet, it is created (DNS only, automatic TTL).

If you answer yes to the IPv4 question, the A record of the same name is kept
pointed at your public IPv4 address too. Turn off UniFi's built-in Dynamic DNS
for that hostname, or the two will keep overwriting each other.

Logs: `journalctl -u unifi-ddns6`. Next run: `systemctl list-timers unifi-ddns6.timer`.

Everything lives in `/data`, which survives firmware updates. The systemd units
in `/etc/systemd/system` may not; if the timer is gone after an update, re-run
`install.sh`.
