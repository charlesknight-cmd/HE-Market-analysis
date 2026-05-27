#!/usr/bin/env bash
# One-shot server setup for HE Job Market Analysis.
#
# Usage on a fresh Ubuntu 22.04 VM (run as root):
#   REPO_URL=https://github.com/charlesknight-cmd/HE-Market-analysis.git \
#   DOMAIN=jobs.charlesknight.co.uk \
#   bash deploy/setup.sh
#
# DOMAIN is optional — if omitted the dashboard is reachable on port 8501 only.
# A Cloudflare DNS A record pointing DOMAIN → this server's IP must exist first
# (set to "DNS only" / grey cloud, not proxied).

set -euo pipefail

REPO_URL="${REPO_URL:-}"
DOMAIN="${DOMAIN:-}"
INSTALL_DIR="/opt/he-market-analysis"
SERVICE_USER="root"     # Hetzner root-only servers; change to "ubuntu" on DigitalOcean etc.

# ── 1. System packages ────────────────────────────────────────────────────────
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip git ufw nginx \
    certbot python3-certbot-nginx

# ── 2. Firewall ───────────────────────────────────────────────────────────────
ufw allow OpenSSH
ufw allow 80/tcp    # HTTP (nginx)
ufw allow 443/tcp   # HTTPS (nginx + certbot)
ufw allow 8501/tcp  # Streamlit direct access (fallback)
ufw --force enable

# ── 3. Clone / update repo ────────────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating existing checkout..."
    git -C "$INSTALL_DIR" pull
else
    if [ -z "$REPO_URL" ]; then
        echo "ERROR: Set REPO_URL before running, e.g.:"
        echo "  REPO_URL=https://github.com/charlesknight-cmd/HE-Market-analysis.git bash deploy/setup.sh"
        exit 1
    fi
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# ── 4. Python virtual environment ─────────────────────────────────────────────
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# ── 5. Streamlit password ─────────────────────────────────────────────────────
SECRETS="$INSTALL_DIR/.streamlit/secrets.toml"
mkdir -p "$INSTALL_DIR/.streamlit"
if [ ! -f "$SECRETS" ]; then
    cp "$INSTALL_DIR/.streamlit/secrets.toml.example" "$SECRETS"
    echo ""
    echo ">>> ACTION REQUIRED: set a password in $SECRETS"
    echo "    Edit the file and replace 'change-me' with a strong password."
fi

# ── 6. Initialise the database ────────────────────────────────────────────────
cd "$INSTALL_DIR"
"$INSTALL_DIR/venv/bin/python" -c "from db.schema import init_db; init_db()"

# ── 7. Run the scraper once now ───────────────────────────────────────────────
"$INSTALL_DIR/venv/bin/python" -m scraper.run

# ── 8. Cron job (daily at 07:00 UTC) ─────────────────────────────────────────
CRON_LINE="0 7 * * * cd $INSTALL_DIR && $INSTALL_DIR/venv/bin/python -m scraper.run >> /var/log/he-market-scraper.log 2>&1"
( crontab -l 2>/dev/null | grep -v "he-market"; echo "$CRON_LINE" ) | crontab -
echo "Cron job installed: daily scrape at 07:00 UTC"

# ── 9. Systemd service for Streamlit ─────────────────────────────────────────
sed "s|ubuntu|$SERVICE_USER|g; s|/opt/he-market-analysis|$INSTALL_DIR|g" \
    "$INSTALL_DIR/deploy/he-market-dashboard.service" \
    > /etc/systemd/system/he-market-dashboard.service

systemctl daemon-reload
systemctl enable he-market-dashboard
systemctl restart he-market-dashboard

# ── 10. nginx reverse proxy ───────────────────────────────────────────────────
cp "$INSTALL_DIR/deploy/nginx.conf" /etc/nginx/sites-available/he-dashboard
ln -sf /etc/nginx/sites-available/he-dashboard /etc/nginx/sites-enabled/he-dashboard
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── 11. TLS certificate (only if DOMAIN is set) ───────────────────────────────
if [ -n "$DOMAIN" ]; then
    # Update the nginx config to use the actual domain
    sed -i "s|jobs.charlesknight.co.uk|$DOMAIN|g" /etc/nginx/sites-available/he-dashboard
    nginx -t && systemctl reload nginx
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@${DOMAIN#*.}"
    echo "TLS certificate installed for $DOMAIN"
else
    echo "No DOMAIN set — skipping TLS. Dashboard reachable at http://$(curl -s ifconfig.me):8501"
fi

echo ""
echo "================================================================"
if [ -n "$DOMAIN" ]; then
    echo " Dashboard: https://$DOMAIN"
else
    echo " Dashboard: http://$(curl -s ifconfig.me):8501"
fi
echo " Scraper log: /var/log/he-market-scraper.log"
echo " To check status: systemctl status he-market-dashboard"
echo "================================================================"
