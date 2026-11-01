#!/bin/bash
# Installs a systemd timer per hostname that runs the DDNS update every 4 minutes.
# Each /data/unifi-ddns6/<name>.env gets its own unifi-ddns6@<name>.timer.
# Everything lives in /data (survives firmware updates); the units in /etc may not,
# so re-run this after a firmware update if `systemctl list-timers 'unifi-ddns6@*'` is empty.
set -euo pipefail

DIR=/data/unifi-ddns6

cat > /etc/systemd/system/unifi-ddns6@.service <<EOF
[Unit]
Description=UniFi Dynamic DNS update (%i)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
EnvironmentFile=$DIR/%i.env
ExecStart=/usr/bin/python3 $DIR/dynamic_dns.py
TimeoutStartSec=90
EOF

cat > /etc/systemd/system/unifi-ddns6@.timer <<EOF
[Unit]
Description=Run UniFi Dynamic DNS update (%i) every 4 minutes

[Timer]
OnBootSec=4min
OnUnitActiveSec=4min

[Install]
WantedBy=timers.target
EOF

# Migrate from the single-hostname setup (unifi-ddns6.timer + .env)
if [ -e /etc/systemd/system/unifi-ddns6.timer ]; then
  systemctl disable --now unifi-ddns6.timer 2>/dev/null || true
  rm -f /etc/systemd/system/unifi-ddns6.timer /etc/systemd/system/unifi-ddns6.service
fi
if [ -f "$DIR/.env" ] && [ ! -e "$DIR/home.env" ]; then
  mv "$DIR/.env" "$DIR/home.env"
fi

systemctl daemon-reload

shopt -s nullglob
envs=("$DIR"/*.env)
if [ ${#envs[@]} -eq 0 ]; then
  echo "No hostnames configured yet. Run $DIR/set-secrets.sh to add one."
  exit 0
fi
for f in "${envs[@]}"; do
  systemctl enable --now "unifi-ddns6@$(basename "$f" .env).timer"
done
systemctl list-timers 'unifi-ddns6@*' --no-pager
