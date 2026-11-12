"""Conexão com o servidor numa thread separada, para não travar a renderização."""

from __future__ import annotations

import threading
import time
from collections import deque

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from client.tunnel import NGROK_HEADERS
from shared import protocol as p

RECONNECT_SECONDS = 20.0


class NetClient:
    def __init__(self, url: str, name: str, password: str = "", token: str = "") -> None:
        self.url, self.name, self.password, self.token = url, name, password, token
        self.player_id: int | None = None
        self.phase = "lobby"
        self.lobby: dict = {}
        self.game_start: dict | None = None
        self.game_gen = 0  # incrementa a cada game_start (a tela de sala observa isto)
        self.snapshots: deque[dict] = deque()
        self.connected = False
        self.reconnecting = False
        self.closing = False
        self.error: str | None = None
        self._ws = None

    def connect(self) -> None:
        # __enter__ = uso "de contexto" sem bloco with (a conexão vive além desta função)
        self._ws = connect(self.url, open_timeout=10, additional_headers=NGROK_HEADERS,
                           compression=None).__enter__()
        self._ws.send(p.encode(p.HELLO, name=self.name, token=self.token,
                               password=self.password, version=p.PROTOCOL_VERSION))
        msg = p.decode(self._ws.recv(timeout=5))
        if msg["t"] == p.ERROR:
            self._ws.close()
            raise ConnectionError(msg.get("reason", "recusado pelo servidor"))
        self._welcome(msg)
        self.connected = True
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def _welcome(self, msg: dict) -> None:
        self.player_id, self.token, self.phase = msg["player_id"], msg["token"], msg["phase"]

    def _recv_loop(self) -> None:
        try:
            for raw in self._ws:
                msg = p.decode(raw)
                t = msg["t"]
                if t == p.SNAPSHOT:
                    self.snapshots.append(msg)
                elif t == p.LOBBY:
                    self.lobby = msg
                    self.phase = msg["phase"]
                elif t == p.GAME_START:
                    self.snapshots.clear()
                    self.game_start = msg
                    self.phase = "game"
                    self.game_gen += 1
                elif t == p.WELCOME:
                    self._welcome(msg)
                elif t == p.ERROR:
                    self.error = msg.get("reason")
        except (ConnectionClosed, OSError):
            pass
        finally:
            self.connected = False
            if not self.closing and self.phase == "game" and self.token:
                self.reconnecting = True
                threading.Thread(target=self._reconnect_loop, daemon=True).start()

    def _reconnect_loop(self, seconds: float = RECONNECT_SECONDS) -> None:
        """Caiu no meio da partida: tenta voltar com o mesmo token (o servidor guarda a vaga)."""
        deadline = time.monotonic() + seconds
        try:
            while time.monotonic() < deadline and not self.closing:
                try:
                    self.connect()
                    return
                except Exception:
                    time.sleep(1.0)
            self.error = "conexão perdida"
        finally:
            self.reconnecting = False

    # ------------------------------------------------------------------ envio
    def _send(self, msg_type: str, **fields) -> None:
        if not self.connected:
            return
        try:
            self._ws.send(p.encode(msg_type, **fields))
        except (ConnectionClosed, OSError):
            self.connected = False

    def send_pick(self, fighter: str) -> None:
        self._send(p.PICK, fighter=fighter)

    def send_ready(self, ready: bool) -> None:
        self._send(p.READY, ready=ready)

    def send_stage(self, stage: str) -> None:
        self._send(p.STAGE, stage=stage)

    def send_bot_level(self, level: str) -> None:
        self._send(p.BOTS, level=level)

    def send_add_bot(self) -> None:
        self._send(p.ADD_BOT)

    def send_remove_bot(self) -> None:
        self._send(p.REMOVE_BOT)

    def send_start(self) -> None:
        self._send(p.START)

    def send_inputs(self, entries: list[tuple[int, int]]) -> None:
        self._send(p.INPUT, inputs=entries)

    def me(self) -> dict | None:
        return next((pl for pl in self.lobby.get("players", []) if pl["id"] == self.player_id),
                    None)

    def is_host(self) -> bool:
        return self.lobby.get("host") == self.player_id

    def close(self) -> None:
        self.closing = True
        self._send(p.LEAVE)
        if self._ws is not None:
            try:
                self._ws.close()
            except OSError:
                pass
        self.connected = False
