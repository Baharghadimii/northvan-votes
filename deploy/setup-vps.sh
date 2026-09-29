#!/usr/bin/env bash
# Run once on the VPS, as a user with sudo.
#   bash ~/northvan-votes/deploy/setup-vps.sh
#
# Installs Caddy, creates the web root, and serves the site over HTTPS.
# Caddy gets and renews certificates by itself — no certbot, no renewal cron.
set -euo pipefail

WEBROOT="/var/www/northvanvotes"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Installing Caddy"
if ! command -v caddy >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y caddy
else
  echo "    already installed: $(caddy version)"
fi

echo "==> Creating web root at ${WEBROOT}"
sudo mkdir -p "$WEBROOT"
# Owned by the deploying user so rsync needs no sudo; readable by Caddy.
sudo chown -R "$USER":"$USER" "$WEBROOT"
sudo chmod 755 "$WEBROOT"

echo "==> Installing Caddyfile"
sudo cp "$REPO_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile

echo "==> Opening ports 80 and 443"
if command -v ufw >/dev/null && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
fi

echo "==> Restarting Caddy"
sudo systemctl enable caddy
sudo systemctl restart caddy
sleep 2
sudo systemctl --no-pager status caddy | head -8

cat <<'DONE'

Done. Next, from your Mac:

    bash deploy/deploy.sh

Certificates are issued on the first HTTPS request once DNS points here,
so make sure the A record exists before testing.
DONE
