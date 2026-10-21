#!/usr/bin/env bash
# Installs (or updates) the bot as a systemd service.
#   sudo bash install.sh          first run asks for the token, API key and admin ID
#   sudo bash install.sh --setup  ask for them again
set -euo pipefail

APP_DIR=/opt/fitbot
ENV_FILE="$APP_DIR/.env"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
    echo "Запусти через sudo: sudo bash $0"
    exit 1
fi

# Replace KEY=... in .env (values are passed via the environment, so any characters are safe).
set_env() {
    K="$1" V="$2" awk -F= '$1 == ENVIRON["K"] { print ENVIRON["K"] "=" ENVIRON["V"]; next } { print }' \
        "$ENV_FILE" > "$ENV_FILE.tmp"
    mv "$ENV_FILE.tmp" "$ENV_FILE"
}

ask() {  # ask VAR "prompt" [secret]
    local answer
    if [ "${3:-}" = secret ]; then
        read -r -s -p "$2" answer < /dev/tty
        echo
    else
        read -r -p "$2" answer < /dev/tty
    fi
    printf -v "$1" '%s' "$(echo "$answer" | tr -d '[:space:]')"
}

setup() {
    echo
    echo "=== Настройка бота ==="
    echo "Секретные значения при вставке не отображаются — это нормально."
    echo

    while true; do
        ask BOT_TOKEN "1/3. Токен бота от @BotFather: " secret
        if [[ ! "$BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]{30,}$ ]]; then
            echo "   Не похоже на токен. Он выглядит так: 123456789:AAH...xyz"
            continue
        fi
        bot_info="$(curl -s --max-time 10 "https://api.telegram.org/bot$BOT_TOKEN/getMe" || true)"
        if [[ "$bot_info" == *'"ok":true'* ]]; then
            echo "   ✓ Бот найден: @$(echo "$bot_info" | sed -n 's/.*"username":"\([^"]*\)".*/\1/p')"
            break
        elif [[ "$bot_info" == *'"ok":false'* ]]; then
            echo "   Telegram не принял этот токен. Проверь его в @BotFather и вставь ещё раз."
        else
            echo "   ⚠ Не получилось проверить токен (нет связи с Telegram), сохраняю как есть."
            break
        fi
    done

    while true; do
        ask API_KEY "2/3. Ключ нейросети (OpenRouter sk-or-..., Groq gsk_... или Claude sk-ant-...): " secret
        [ -n "$API_KEY" ] && break
        echo "   Ключ не может быть пустым."
    done
    case "$API_KEY" in
        sk-ant-*)
            set_env AI_PROVIDER claude
            set_env ANTHROPIC_API_KEY "$API_KEY"
            echo "   ✓ Claude API" ;;
        gsk_*)
            set_env AI_PROVIDER openai
            set_env OPENAI_BASE_URL https://api.groq.com/openai/v1
            set_env OPENAI_MODEL openai/gpt-oss-120b
            set_env OPENAI_API_KEY "$API_KEY"
            echo "   ✓ Groq (бесплатно)" ;;
        *)
            set_env AI_PROVIDER openai
            set_env OPENAI_BASE_URL https://openrouter.ai/api/v1
            set_env OPENAI_MODEL openai/gpt-oss-120b:free
            set_env OPENAI_API_KEY "$API_KEY"
            echo "   ✓ OpenRouter (бесплатные модели)" ;;
    esac

    while true; do
        ask ADMIN_ID "3/3. Твой Telegram ID (узнать: напиши @userinfobot): "
        [[ "$ADMIN_ID" =~ ^[0-9]+$ ]] && break
        echo "   ID — это только цифры, например 123456789."
    done

    ask FRIENDS "Необязательно: ID друзей через запятую (Enter — бот будет открыт всем): "
    set_env BOT_TOKEN "$BOT_TOKEN"
    set_env ADMIN_ID "$ADMIN_ID"
    set_env ALLOWED_USERS "$FRIENDS"
    echo
    echo "✓ Настройки сохранены в $ENV_FILE"
}

echo ">>> Ставлю системные пакеты…"
apt-get update -qq
apt-get install -y -qq python3-venv curl > /dev/null

id -u fitbot &>/dev/null || useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin fitbot
mkdir -p "$APP_DIR"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
    # Code only: never overwrite the server's .env or database.
    cp -r "$SRC_DIR"/*.py "$SRC_DIR"/handlers "$SRC_DIR"/requirements.txt "$SRC_DIR"/.env.example "$APP_DIR"/
fi

if [ ! -f "$ENV_FILE" ]; then
    cp "$APP_DIR/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    setup
elif [ "${1:-}" = "--setup" ]; then
    setup
fi

echo ">>> Ставлю зависимости Python (пару минут)…"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R fitbot:fitbot "$APP_DIR"
chmod 600 "$ENV_FILE"

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
sleep 5

echo
if systemctl is-active --quiet fitbot; then
    echo "✅ Бот запущен! Напиши ему в Telegram /start"
    echo "   Проверить связь с нейросетью: отправь боту /proxy и нажми «Проверить связь»"
else
    echo "❌ Бот не запустился. Последние строки лога:"
    journalctl -u fitbot -n 20 --no-pager
fi
echo
echo "Логи:              journalctl -u fitbot -f"
echo "Изменить настройки: sudo bash $SRC_DIR/install.sh --setup"
