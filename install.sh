#!/usr/bin/env bash
# Installs (or updates) the bot as a systemd service. Run: sudo bash install.sh
set -euo pipefail

APP_DIR=/opt/fitbot
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

apt-get update -qq
apt-get install -y -qq python3-venv

id -u fitbot &>/dev/null || useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin fitbot
mkdir -p "$APP_DIR"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
    # Code only: never overwrite the server's .env or database.
    cp -r "$SRC_DIR"/*.py "$SRC_DIR"/handlers "$SRC_DIR"/requirements.txt "$SRC_DIR"/.env.example "$APP_DIR"/
fi

if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo
    echo ">>> Заполни настройки: nano $APP_DIR/.env"
    echo ">>> Потом запусти этот скрипт ещё раз."
    exit 0
fi

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R fitbot:fitbot "$APP_DIR"
chmod 600 "$APP_DIR/.env"

cat > /etc/systemd/system/fitbot.service <<EOF
[Unit]
Description=Fitness trainer Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
User=fitbot
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python bot.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
# Keep the bot from starving the other services on a small server.
MemoryMax=250M

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable fitbot -q
systemctl restart fitbot
sleep 3
systemctl --no-pager status fitbot | head -n 5
echo
echo ">>> Готово! Логи: journalctl -u fitbot -f"
