"""Integração: servidor de verdade (WebSocket) + clientes de verdade (NetClient)."""

import asyncio
import socket
import threading
import time

import pytest

from client.net import NetClient
from server.game_server import GameServer
from shared import inputs as I


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server_url():
    port = _free_port()
    ready = threading.Event()
    holder: dict = {}

    def run():
        async def main():
            ev = asyncio.Event()
            srv = GameServer()
            holder["srv"] = srv
            task = asyncio.create_task(srv.run("127.0.0.1", port, ev))
            await ev.wait()
            ready.set()
            await task

        asyncio.run(main())

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(5)
    yield f"ws://127.0.0.1:{port}", holder["srv"]


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_lobby_start_inputs_snapshots_and_reconnect(server_url):
    url, srv = server_url
    host = NetClient(url, "Ana")
    host.connect()
    guest = NetClient(url, "Bia")
    guest.connect()
    assert wait_for(lambda: len(host.lobby.get("players", [])) == 2)
    assert host.is_host() and not guest.is_host()

    host.send_pick("lince")
    host.send_add_bot()
    guest.send_ready(True)
    assert wait_for(lambda: host.lobby.get("can_start")
                    and len(host.lobby["players"]) == 3)
    host.send_start()
    assert wait_for(lambda: host.game_gen == 1 and guest.game_gen == 1)
    assert [r["fighter"] for r in host.game_start["roster"]][0] == "lince"

    # manda inputs numerados e confere o ack voltando nos snapshots
    for seq in range(1, 31):
        host.send_inputs([(seq, I.RIGHT)])
        time.sleep(1 / 60)
    assert wait_for(lambda: any(s.get("ack") == 30 for s in list(host.snapshots)))

    # a conexão do guest cai: o cliente reconecta sozinho com o token e recupera a vaga
    gid = guest.player_id
    guest._ws.close()
    assert wait_for(lambda: guest.game_gen == 2 and guest.connected, timeout=8)
    assert guest.player_id == gid and gid not in srv.bots

    # um estranho não entra no meio da partida
    with pytest.raises(ConnectionError):
        NetClient(url, "Intruso").connect()

    # saída intencional não reconecta
    guest.close()
    time.sleep(0.3)
    assert not guest.reconnecting and gid in srv.bots
    host.close()
    assert wait_for(lambda: srv.phase == "lobby")
