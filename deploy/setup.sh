#!/usr/bin/env bash
# One-shot server setup for HE Job Market Analysis.
# Run as root on a fresh Ubuntu 22.04 VM:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_REPO/main/deploy/setup.sh | bash
# Or copy to the server and run: bash deploy/setup.sh

set -euo pipefail

REPO_URL="${REPO_URL:-}"          # set via env or edit below
INSTALL_DIR="/opt/he-market-analysis"
SERVICE_USER="ubuntu"             # default Hetzner/DigitalOcean user

# ── 1. System packages ────────────────────────────────────────────────────────
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip git ufw

# ── 2. Firewall ───────────────────────────────────────────────────────────────
ufw allow OpenSSH
ufw allow 8501/tcp   # Streamlit
ufw --force enable

# ── 3. Clone / update repo ────────────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating existing checkout..."
    git -C "$INSTALL_DIR" pull
else
    if [ -z "$REPO_URL" ]; then
        echo "ERROR: Set REPO_URL before running, e.g.:"
        echo "  REPO_URL=https://github.com/you/he-market-analysis bash deploy/setup.sh"
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
"$INSTALL_DIR/venv/bin/python" -m db.schema 2>/dev/null || \
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

echo ""
echo "================================================================"
echo " Setup complete."
echo " Dashboard: http://$(curl -s ifconfig.me):8501"
echo " Scraper log: /var/log/he-market-scraper.log"
echo " To check status: systemctl status he-market-dashboard"
echo "================================================================"
