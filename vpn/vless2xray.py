"""Convert a vless:// share link into an Xray client config with a local socks5 inbound.

Usage: python3 vless2xray.py "vless://..." [socks_port] > config.json
"""
import json
import sys
from urllib.parse import parse_qs, unquote, urlsplit

NETWORKS = {"tcp", "raw", "ws", "grpc", "httpupgrade", "xhttp", "splithttp", "kcp", "mkcp", "h2", "http"}


def fail(message: str):
    print(f"Ошибка: {message}", file=sys.stderr)
    sys.exit(1)


def stream_settings(q: dict[str, str], host: str) -> dict:
    network = q.get("type", "tcp").lower()
    if network not in NETWORKS:
        fail(f"неизвестный тип транспорта «{network}»")
    network = {"raw": "tcp", "splithttp": "xhttp", "mkcp": "kcp", "h2": "http"}.get(network, network)
    security = q.get("security", "none").lower()
    path = unquote(q.get("path", "/"))
    host_header = q.get("host", "")

    stream: dict = {"network": network, "security": security}
    if security == "reality":
        if not q.get("pbk"):
            fail("в ссылке с security=reality нет параметра pbk (публичный ключ)")
        stream["realitySettings"] = {
            "serverName": q.get("sni", ""),
            "fingerprint": q.get("fp", "chrome"),
            "publicKey": q["pbk"],
            "shortId": q.get("sid", ""),
            "spiderX": unquote(q.get("spx", "")),
        }
    elif security == "tls":
        tls = {"serverName": q.get("sni") or host_header or host, "fingerprint": q.get("fp", "chrome")}
        if q.get("alpn"):
            tls["alpn"] = unquote(q["alpn"]).split(",")
        if q.get("allowInsecure") in {"1", "true"}:
            tls["allowInsecure"] = True
        stream["tlsSettings"] = tls
    elif security != "none":
        fail(f"неизвестный тип шифрования «{security}»")

    if network == "ws":
        stream["wsSettings"] = {"path": path, "host": host_header}
    elif network == "grpc":
        stream["grpcSettings"] = {"serviceName": unquote(q.get("serviceName", "")), "multiMode": q.get("mode") == "multi"}
    elif network == "httpupgrade":
        stream["httpupgradeSettings"] = {"path": path, "host": host_header}
    elif network == "xhttp":
        stream["xhttpSettings"] = {"path": path, "host": host_header, "mode": q.get("mode", "auto")}
    elif network == "http":
        stream["httpSettings"] = {"path": path, "host": [host_header] if host_header else []}
    elif network == "kcp":
        stream["kcpSettings"] = {"header": {"type": q.get("headerType", "none")}, "seed": q.get("seed", "")}
    elif network == "tcp" and q.get("headerType") == "http":
        stream["tcpSettings"] = {"header": {"type": "http", "request": {
            "path": [path], "headers": {"Host": [host_header]} if host_header else {}}}}
    return stream


def convert(link: str, socks_port: int) -> dict:
    link = link.strip()
    if not link.startswith("vless://"):
        fail("ссылка должна начинаться с vless://")
    parts = urlsplit(link)
    try:
        port = parts.port
    except ValueError:
        port = None
    uuid = unquote(parts.username or "")
    if not uuid or not parts.hostname or not port:
        fail("в ссылке не хватает UUID, адреса сервера или порта")
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}

    user = {"id": uuid, "encryption": q.get("encryption", "none")}
    if q.get("flow"):
        user["flow"] = q["flow"]
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "tag": "socks-in",
            "listen": "127.0.0.1",
            "port": socks_port,
            "protocol": "socks",
            "settings": {"udp": False},
        }],
        "outbounds": [{
            "tag": "vless-out",
            "protocol": "vless",
            "settings": {"vnext": [{"address": parts.hostname, "port": port, "users": [user]}]},
            "streamSettings": stream_settings(q, parts.hostname),
        }],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        fail('укажи ссылку: python3 vless2xray.py "vless://..." [порт]')
    print(json.dumps(convert(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 10818), indent=2, ensure_ascii=False))
