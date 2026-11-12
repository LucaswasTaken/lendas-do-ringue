"""Abre um túnel do ngrok para a porta do jogo e descobre o link público.

Requer o ngrok instalado e configurado uma vez:
    winget install ngrok.ngrok
    ngrok config add-authtoken <seu token de https://dashboard.ngrok.com>
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.request

NGROK_API = "http://127.0.0.1:4040/api/tunnels"


def public_urls(port: int, timeout: float = 0.5) -> list[str]:
    """Links públicos dos túneis do ngrok deste PC que apontam para `port` (https primeiro)."""
    try:
        with urllib.request.urlopen(NGROK_API, timeout=timeout) as resp:
            data = json.load(resp)
    except (OSError, ValueError):
        return []
    urls = set()
    for t in data.get("tunnels", []):
        public = t.get("public_url", "")
        addr = str(t.get("config", {}).get("addr", "")).rstrip("/")
        if public and (addr.endswith(f":{port}") or addr == str(port)):
            urls.add(public)
    return sorted(urls, key=lambda u: (not u.startswith("https"), u))


def start(port: int, wait: float = 15.0) -> tuple[subprocess.Popen | None, str | None, str]:
    """Inicia `ngrok http <port>` (se ainda não houver túnel). Devolve (processo, link, aviso)."""
    existing = public_urls(port)
    if existing:
        return None, existing[0], "usando um túnel do ngrok que já estava aberto"
    exe = shutil.which("ngrok")
    if exe is None:
        return None, None, ("ngrok não encontrado. Instale com `winget install ngrok.ngrok` e rode "
                            "`ngrok config add-authtoken <token>` uma vez.")
    proc = subprocess.Popen([exe, "http", str(port), "--log", "stdout"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return None, None, ("o ngrok fechou sozinho — falta configurar o token? "
                                "Rode `ngrok config add-authtoken <token>`.")
        urls = public_urls(port)
        if urls:
            return proc, urls[0], ""
        time.sleep(0.5)
    return proc, None, "o ngrok não informou o link a tempo; veja http://127.0.0.1:4040"
