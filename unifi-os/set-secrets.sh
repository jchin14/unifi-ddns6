#!/bin/bash
# Prompts for settings and writes /data/unifi-ddns6/<name>.env (root-only, 600),
# then enables its timer and runs a test update.
# Usage: set-secrets.sh [name]   (default: home; one name per hostname, e.g. home, secondary)
set -euo pipefail

DIR=/data/unifi-ddns6
NAME=${1:-home}
[[ $NAME =~ ^[A-Za-z0-9_-]+$ ]] || { echo "Name may only contain letters, digits, - and _"; exit 1; }
ENV=$DIR/$NAME.env

# systemd EnvironmentFile double-quoted value: escape backslashes and quotes
q() { local v=${1//\\/\\\\}; v=${v//\"/\\\"}; printf '"%s"' "$v"; }

# Offer to reuse credentials from another hostname's file
CREDS=""
shopt -s nullglob
for other in "$DIR"/*.env; do
  [ "$other" = "$ENV" ] && continue
  read -rp "Reuse UniFi and Cloudflare credentials from $(basename "$other" .env)? [Y/n] " reuse
  if [[ ! $reuse =~ ^[Nn] ]]; then
    CREDS=$(grep -E '^(UNIFI_CONTROLLER_URL|UNIFI_SITE_NAME|UNIFI_API_USERNAME|UNIFI_API_PASSWORD|CLOUDFLARE_ZONE_ID|CLOUDFLARE_API_TOKEN)=' "$other")
  fi
  break
done

if [ -z "$CREDS" ]; then
  read -rp  "UniFi View Only username: " UNIFI_USER
  read -rsp "UniFi View Only password: " UNIFI_PASS; echo
  read -rp  "Cloudflare Zone ID (zone Overview page, right sidebar): " CF_ZONE
  read -rsp "Cloudflare API token (Zone > DNS > Edit): " CF_TOKEN; echo
  CREDS="UNIFI_CONTROLLER_URL=https://127.0.0.1
UNIFI_SITE_NAME=default
UNIFI_API_USERNAME=$(q "$UNIFI_USER")
UNIFI_API_PASSWORD=$(q "$UNIFI_PASS")
CLOUDFLARE_ZONE_ID=$(q "$CF_ZONE")
CLOUDFLARE_API_TOKEN=$(q "$CF_TOKEN")"
fi

read -rp "Cloudflare record name (e.g. home.example.com): " CF_RECORD
read -rp "Which WAN? [wan1] (wan1 = primary, wan2 = secondary) " WAN
WAN=${WAN:-wan1}
read -rp "Keep the AAAA record pointed at this WAN's IPv6? [Y/n] " CF_V6
[[ $CF_V6 =~ ^[Nn] ]] && CF_V6=false || CF_V6=true
read -rp "Keep the A record pointed at this WAN's public IPv4? [y/N] " CF_V4
[[ $CF_V4 =~ ^[Yy] ]] && CF_V4=true || CF_V4=false

umask 077
cat > "$ENV" <<EOF
DNS_PROVIDER=Cloudflare
CLOUDFLARE_RECORD_NAME=$(q "$CF_RECORD")
UNIFI_WAN=$(q "$WAN")
CLOUDFLARE_UPDATE_IPV6=$CF_V6
CLOUDFLARE_UPDATE_IPV4=$CF_V4
$CREDS
EOF
chmod 600 "$ENV"
echo "Saved $ENV. Running a test update..."
systemctl enable --now "unifi-ddns6@$NAME.timer"
systemctl start "unifi-ddns6@$NAME.service" && echo "OK" || echo "Test run failed"
journalctl -u "unifi-ddns6@$NAME.service" -n 15 --no-pager -o cat
