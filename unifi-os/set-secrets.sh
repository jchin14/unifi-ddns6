#!/bin/bash
# Prompts for credentials and writes /data/unifi-ddns6/.env (root-only, 600).
set -euo pipefail

ENV=/data/unifi-ddns6/.env

# systemd EnvironmentFile double-quoted value: escape backslashes and quotes
q() { local v=${1//\\/\\\\}; v=${v//\"/\\\"}; printf '"%s"' "$v"; }

read -rp  "UniFi View Only username: " UNIFI_USER
read -rsp "UniFi View Only password: " UNIFI_PASS; echo
read -rp  "Cloudflare record name (e.g. home.example.com): " CF_RECORD
read -rp  "Cloudflare Zone ID (zone Overview page, right sidebar): " CF_ZONE
read -rsp "Cloudflare API token (Zone > DNS > Edit): " CF_TOKEN; echo

umask 077
cat > "$ENV" <<EOF
DNS_PROVIDER=Cloudflare
CLOUDFLARE_RECORD_NAME=$(q "$CF_RECORD")
CLOUDFLARE_ZONE_ID=$(q "$CF_ZONE")
CLOUDFLARE_API_TOKEN=$(q "$CF_TOKEN")
UNIFI_CONTROLLER_URL=https://127.0.0.1
UNIFI_SITE_NAME=default
UNIFI_API_USERNAME=$(q "$UNIFI_USER")
UNIFI_API_PASSWORD=$(q "$UNIFI_PASS")
EOF
chmod 600 "$ENV"
echo "Saved $ENV. Running a test update..."
systemctl start unifi-ddns6.service && echo "OK" || echo "Test run failed"
journalctl -u unifi-ddns6.service -n 15 --no-pager -o cat
