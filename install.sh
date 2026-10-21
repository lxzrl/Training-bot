#!/usr/bin/env bash
# Installs (or updates) the bot as a systemd service.
#   sudo bash install.sh          first run asks for the token, API key and admin ID
#   sudo bash install.sh --setup  ask for them again
#   sudo bash install.sh --vpn    set up (or change) the VLESS VPN for AI requests
set -euo pipefail

APP_DIR=/opt/fitbot
ENV_FILE="$APP_DIR/.env"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
XRAY_DIR="$APP_DIR/xray"
VPN_PORT=10818

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
        ask BOT_TOKEN "1/4. Токен бота от @BotFather: " secret
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
        ask API_KEY "2/4. Ключ нейросети (OpenRouter sk-or-..., Groq gsk_... или Claude sk-ant-...): " secret
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
        ask ADMIN_ID "3/4. Твой Telegram ID (узнать: напиши @userinfobot): "
        [[ "$ADMIN_ID" =~ ^[0-9]+$ ]] && break
        echo "   ID — это только цифры, например 123456789."
    done

    ask FRIENDS "   Необязательно: ID друзей через запятую (Enter — бот будет открыт всем): "
    set_env BOT_TOKEN "$BOT_TOKEN"
    set_env ADMIN_ID "$ADMIN_ID"
    set_env ALLOWED_USERS "$FRIENDS"
    setup_vpn
    echo
    echo "✓ Настройки сохранены в $ENV_FILE"
}

install_xray() {
    local asset tmp
    case "$(uname -m)" in
        x86_64) asset=Xray-linux-64.zip ;;
        aarch64 | arm64) asset=Xray-linux-arm64-v8a.zip ;;
        *) echo "   Архитектура $(uname -m) не поддерживается"; return 1 ;;
    esac
    echo "   Скачиваю Xray…"
    tmp="$(mktemp -d)"
    if ! curl -fsSL --max-time 180 -o "$tmp/xray.zip" \
            "https://github.com/XTLS/Xray-core/releases/latest/download/$asset"; then
        echo "   Не получилось скачать Xray с GitHub."
        rm -rf "$tmp"
        return 1
    fi
    python3 -m zipfile -e "$tmp/xray.zip" "$tmp/x"
    install -m 755 "$tmp/x/xray" "$XRAY_DIR/xray"
    rm -rf "$tmp"
}

# The proxy chosen in the bot via /proxy overrides .env; the installer's choice should win.
forget_bot_proxy() {
    [ -f "$APP_DIR/fitbot.db" ] || return 0
    python3 -c "import sqlite3, sys; c = sqlite3.connect(sys.argv[1]); c.execute(\"DELETE FROM settings WHERE key='proxy'\"); c.commit()" \
        "$APP_DIR/fitbot.db" 2>/dev/null || true
}

setup_vpn() {
    echo
    echo "Через VPN пойдут только запросы к нейросети, Telegram работает напрямую."
    ask VLESS_LINK "4/4. VLESS-ссылка vless://... (Enter — без VPN): " secret
    if [ -z "$VLESS_LINK" ]; then
        echo "   Без VPN."
        return 0
    fi

    mkdir -p "$XRAY_DIR"
    if ! python3 "$SRC_DIR/vpn/vless2xray.py" "$VLESS_LINK" "$VPN_PORT" > "$XRAY_DIR/config.new.json"; then
        rm -f "$XRAY_DIR/config.new.json"
        echo "   VPN не настроен. Повторить: sudo bash $SRC_DIR/install.sh --vpn"
        return 0
    fi
    if [ ! -x "$XRAY_DIR/xray" ] && ! install_xray; then
        rm -f "$XRAY_DIR/config.new.json"
        echo "   VPN не настроен. Повторить: sudo bash $SRC_DIR/install.sh --vpn"
        return 0
    fi
    if ! "$XRAY_DIR/xray" run -test -c "$XRAY_DIR/config.new.json" > /dev/null 2>&1; then
        rm -f "$XRAY_DIR/config.new.json"
        echo "   Xray не принял настройки из этой ссылки. Проверь её и повтори: sudo bash $SRC_DIR/install.sh --vpn"
        return 0
    fi
    mv "$XRAY_DIR/config.new.json" "$XRAY_DIR/config.json"
    chmod 600 "$XRAY_DIR/config.json"
    chown -R fitbot:fitbot "$XRAY_DIR"

    cat > /etc/systemd/system/fitbot-vpn.service <<EOF
[Unit]
Description=VLESS client for fitbot (local socks5 proxy on 127.0.0.1:$VPN_PORT)
After=network-online.target
Wants=network-online.target

[Service]
User=fitbot
ExecStart=$XRAY_DIR/xray run -c $XRAY_DIR/config.json
Restart=always
RestartSec=5
MemoryMax=100M

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable fitbot-vpn -q
    systemctl restart fitbot-vpn
    sleep 3

    echo "   Проверяю VPN…"
    local ip
    ip="$(curl -s --max-time 15 --socks5-hostname "127.0.0.1:$VPN_PORT" https://api.ipify.org || true)"
    forget_bot_proxy
    if [ -n "$ip" ]; then
        echo "   ✓ VPN работает, внешний IP: $ip"
        set_env PROXY_URL "socks5://127.0.0.1:$VPN_PORT"
    else
        echo "   ❌ VPN не отвечает. Последние строки лога:"
        journalctl -u fitbot-vpn -n 10 --no-pager || true
        echo "   Пока нейросеть будет работать без VPN. Повторить: sudo bash $SRC_DIR/install.sh --vpn"
        set_env PROXY_URL ""
    fi
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
elif [ "${1:-}" = "--vpn" ]; then
    setup_vpn
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
if systemctl is-enabled --quiet fitbot-vpn 2>/dev/null; then
    if systemctl is-active --quiet fitbot-vpn; then echo "🛡 VPN для нейросети: работает"; else echo "🛡 VPN для нейросети: не запущен"; fi
fi
echo
echo "Логи бота:          journalctl -u fitbot -f"
echo "Логи VPN:           journalctl -u fitbot-vpn -f"
echo "Изменить настройки: sudo bash $SRC_DIR/install.sh --setup"
echo "Изменить VPN:       sudo bash $SRC_DIR/install.sh --vpn"
