"""Serve o cliente de navegador (web/) e os assets pela MESMA porta do WebSocket.

Assim um único túnel (`ngrok http 8766`) entrega a página, os sons e o jogo:
- requisição com `Upgrade: websocket`  -> segue para o servidor do jogo;
- GET /                                -> web/index.html
- GET /js/... /css/... /vendor/...     -> arquivos de web/
- GET /assets/...                      -> arquivos de assets/
- GET /api/content.json                -> lutadores, palcos e constantes da sim
- GET /api/info                        -> se a sala pede senha e a fase atual
"""

from __future__ import annotations

import json
import mimetypes
from collections.abc import Callable
from dataclasses import asdict
from functools import lru_cache
from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote, urlsplit

from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from shared import constants
from shared import protocol as p
from shared.content import fighters, stages
from shared.paths import assets_dir, project_root

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".wav": "audio/wav",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def web_dir() -> Path:
    return project_root() / "web"


def build_content() -> dict:
    """Tudo que o cliente de navegador precisa para desenhar e prever (mesma sim em JS)."""
    fs = {}
    for key, f in fighters().items():
        d = asdict(f)
        for mk, m in d["moves"].items():
            m["total"] = f.moves[mk].total
            m["impulse"] = list(m["impulse"]) if m["impulse"] else None
        fs[key] = d
    sts = {}
    for key, s in stages().items():
        d = asdict(s)
        d["blast"] = list(s.blast)
        d["spawns"] = [list(sp) for sp in s.spawns]
        sts[key] = d
    consts = {k: getattr(constants, k) for k in dir(constants) if k.isupper()}
    return {"fighters": fs, "stages": sts, "constants": consts,
            "protocol_version": p.PROTOCOL_VERSION}


def _no_info() -> dict:
    return {"password": False, "phase": "lobby"}


# GameServer.run troca por GameServer.info (se a sala tem senha, fase atual)
info_provider: Callable[[], dict] = _no_info


@lru_cache(maxsize=1)
def content_json() -> bytes:
    return json.dumps(build_content(), ensure_ascii=False, default=list).encode("utf-8")


def _response(status: HTTPStatus, body: bytes, content_type: str, cache: str = "no-cache"
              ) -> Response:
    headers = Headers()
    headers["Content-Type"] = content_type
    headers["Content-Length"] = str(len(body))
    headers["Cache-Control"] = cache
    headers["Connection"] = "close"
    return Response(status.value, status.phrase, headers, body)


def _not_found() -> Response:
    return _response(HTTPStatus.NOT_FOUND, b"404 - nao encontrado", "text/plain; charset=utf-8")


def _safe_file(base: Path, rel: str) -> Path | None:
    """Arquivo dentro de `base` (bloqueia ../, caminhos absolutos e afins)."""
    base = base.resolve()
    try:
        path = (base / rel).resolve()
    except (OSError, ValueError):
        return None
    if base != path and base not in path.parents:
        return None
    return path if path.is_file() else None


def _content_type(path: Path) -> str:
    return MIME.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or \
        "application/octet-stream"


def handle_http(path: str) -> Response:
    path = unquote(urlsplit(path).path)
    if "\x00" in path or "\\" in path:
        return _not_found()
    if path in ("/", "/index.html"):
        f = _safe_file(web_dir(), "index.html")
        return _response(HTTPStatus.OK, f.read_bytes(), MIME[".html"]) if f else _not_found()
    if path == "/api/content.json":
        return _response(HTTPStatus.OK, content_json(), MIME[".json"])
    if path == "/api/info":
        return _response(HTTPStatus.OK, json.dumps(info_provider()).encode(), MIME[".json"])
    rel = path.lstrip("/")
    if rel.startswith("assets/"):
        f = _safe_file(assets_dir(), rel[len("assets/"):])
        cache = "public, max-age=3600"
    elif rel.split("/", 1)[0] in ("js", "css", "vendor"):
        f = _safe_file(web_dir(), rel)
        cache = "no-cache"
    else:
        f, cache = None, ""
    if f is None:
        return _not_found()
    return _response(HTTPStatus.OK, f.read_bytes(), _content_type(f), cache)


def process_request(connection, request: Request) -> Response | None:
    """Gancho do websockets: devolve uma página HTTP, ou None para seguir com o WebSocket."""
    if "websocket" in request.headers.get("Upgrade", "").lower():
        return None
    return handle_http(request.path)
