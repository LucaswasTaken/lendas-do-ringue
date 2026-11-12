"""Converte o endereço digitado pelo jogador numa URL de WebSocket (inclui links do ngrok)."""

from __future__ import annotations

from urllib.parse import urlsplit

from shared.constants import DEFAULT_PORT

NGROK_DOMAINS = (".ngrok-free.app", ".ngrok-free.dev", ".ngrok.app", ".ngrok.dev", ".ngrok.io")
# o ngrok gratuito mostra um aviso para navegadores; este cabeçalho pula o aviso
NGROK_HEADERS = {"ngrok-skip-browser-warning": "1"}


def is_ngrok_host(host: str) -> bool:
    return host.lower().endswith(NGROK_DOMAINS)


def normalize_server_url(text: str) -> str:
    """192.168.0.5 -> ws://192.168.0.5:8766 · https://x.ngrok-free.app -> wss://x.ngrok-free.app"""
    url = (text or "").strip().rstrip("/")
    if not url:
        return f"ws://127.0.0.1:{DEFAULT_PORT}"
    scheme, sep, rest = url.partition("://")
    if not sep:
        scheme, rest = "", url
    scheme = scheme.lower()
    if scheme in ("ws", "wss"):
        return f"{scheme}://{rest}"
    if scheme == "https":
        return f"wss://{rest}"
    if scheme in ("http", "tcp"):
        return f"ws://{rest}"
    parts = urlsplit(f"//{rest}")
    host = parts.hostname or rest
    if is_ngrok_host(host) and parts.port is None:
        return f"wss://{rest}"
    return f"ws://{rest}" if parts.port is not None else f"ws://{rest}:{DEFAULT_PORT}"
