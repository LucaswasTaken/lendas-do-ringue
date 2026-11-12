"""Servidor HTTP do cliente de navegador + cliente web rodando no Node contra o servidor real."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from server.web import handle_http
from tests.test_server import server_url  # noqa: F401 - fixture reaproveitada

NODE = shutil.which("node")


def test_serves_page_assets_and_content():
    r = handle_http("/")
    assert r.status_code == 200 and b"Lendas do Ringue" in r.body
    assert handle_http("/js/sim.js").status_code == 200
    assert handle_http("/vendor/msgpack.min.js").status_code == 200
    assert handle_http("/assets/sounds/hit.wav").status_code == 200
    content = json.loads(handle_http("/api/content.json").body)
    assert {"ravena", "toro", "lince", "ondina"} <= set(content["fighters"])
    assert content["constants"]["TICK_RATE"] == 60
    assert content["fighters"]["toro"]["moves"]["heavy_side"]["total"] > 0


@pytest.mark.parametrize("path", ["/../pyproject.toml", "/js/../../shared/sim.py",
                                  "/assets/../server/web.py", "/js/%2e%2e/%2e%2e/README.md",
                                  "/shared/sim.py"])
def test_blocks_paths_outside_web_and_assets(path):
    assert handle_http(path).status_code == 404


@pytest.mark.skipif(NODE is None, reason="Node.js não instalado")
def test_browser_client_plays_against_real_server(server_url):  # noqa: F811
    url, srv = server_url
    host = url.removeprefix("ws://")
    script = Path(__file__).with_name("web_client_smoke.mjs")
    out = subprocess.run([NODE, str(script), host], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    stats = json.loads(out.stdout.strip().splitlines()[-1])
    assert stats["fighter"] == "ondina"
    assert stats["frame"] > 100  # recebeu snapshots do servidor
    assert stats["pending"] < 30  # o servidor está confirmando os inputs (ack)
    assert stats["drawCalls"] > 1000  # desenhou de fato
