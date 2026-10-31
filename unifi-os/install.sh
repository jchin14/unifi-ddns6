#!/bin/bash
# Installs the systemd timer that runs the IPv6 DDNS update every 2 minutes.
# Everything lives in /data (survives firmware updates); the units in /etc may not,
# so re-run this after a firmware update if `systemctl status unifi-ddns6.timer` is missing.
set -euo pipefail

DIR=/data/unifi-ddns6

cat > /etc/systemd/system/unifi-ddns6.service <<EOF
[Unit]
Description=UniFi IPv6 Dynamic DNS update (Cloudflare)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
EnvironmentFile=$DIR/.env
ExecStart=/usr/bin/python3 $DIR/dynamic_dns.py
TimeoutStartSec=90
EOF

cat > /etc/systemd/system/unifi-ddns6.timer <<EOF
[Unit]
Description=Run UniFi IPv6 DDNS update every 2 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now unifi-ddns6.timer
systemctl list-timers unifi-ddns6.timer --no-pager
