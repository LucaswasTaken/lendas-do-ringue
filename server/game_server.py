"""Servidor autoritativo: sala, partida a 60 Hz (inputs -> sim -> snapshots) e reconexão.

- Cada jogador manda inputs numerados; o servidor aplica 1 por tick (shared/netinput.py) e
  devolve no snapshot o `ack` (último seq aplicado) para o cliente reconciliar a predição.
- Quem cai durante a partida é controlado por um bot até reconectar com o mesmo token.
- Se todos os humanos saírem, a partida acaba e a sala volta a esperar.
- `fake_lag` (segundos, ida + volta) atrasa mensagens para testar a predição em casa.
"""

from __future__ import annotations

import asyncio
import logging
import secrets

from websockets.asyncio.server import ServerConnection, broadcast, serve
from websockets.exceptions import ConnectionClosed

from server import web
from server.bots import BotBrain
from server.lobby import Lobby, Player
from shared import constants as C
from shared import protocol as p
from shared.content import fighters, stages
from shared.netinput import InputQueue
from shared.sim import World

log = logging.getLogger("server")
LOBBY, GAME = "lobby", "game"
RESET_DELAY = 6.0  # segundos mostrando o resultado antes de voltar à sala


class GameServer:
    def __init__(self, password: str | None = None, fake_lag_ms: int = 0) -> None:
        self.password = password or None
        self.fake_lag = max(0, fake_lag_ms) / 1000.0
        self.lobby = Lobby(list(fighters()), list(stages()))
        self.phase = LOBBY
        self.world: World | None = None
        self.queues: dict[int, InputQueue] = {}
        self.bots: dict[int, BotBrain] = {}
        self.clients: dict[int, ServerConnection] = {}
        self.conn_player: dict[ServerConnection, int] = {}
        self.events: list[dict] = []
        self.notice = ""
        self.reset_in: float | None = None
        self._lobby_dirty = True
        self._loop: asyncio.AbstractEventLoop | None = None

    def info(self) -> dict:
        """Informações públicas para a página antes de conectar (/api/info)."""
        return {"password": self.password is not None, "phase": self.phase}

    # ------------------------------------------------------------------ envio
    def _send(self, conns, data: bytes) -> None:
        conns = list(conns)
        if not conns:
            return
        if self.fake_lag and self._loop is not None:
            self._loop.call_later(self.fake_lag / 2, broadcast, conns, data)
        else:
            broadcast(conns, data)

    def _broadcast_lobby(self) -> None:
        st = self.lobby.state(self.phase)
        st["notice"] = self.notice
        self._send(self.clients.values(), p.encode(p.LOBBY, **st))

    # ------------------------------------------------------------------ partida
    def start_game(self) -> None:
        roster_players = sorted(self.lobby.players.values(), key=lambda pl: pl.id)
        fs = fighters()
        self.world = World(stages()[self.lobby.stage],
                           [(pl.id, fs[pl.fighter]) for pl in roster_players])
        self.queues = {pl.id: InputQueue() for pl in roster_players if not pl.bot}
        self.bots = {pl.id: BotBrain(pl.id, self.lobby.bot_level, seed=pl.id)
                     for pl in roster_players if pl.bot or not pl.connected}
        self.events = []
        self.phase, self.reset_in, self.notice = GAME, None, ""
        log.info("partida começou no %s com %d lutadores", self.lobby.stage, len(roster_players))
        self._send(self.clients.values(), self._game_start_msg())

    def _game_start_msg(self) -> bytes:
        assert self.world is not None
        return p.encode(
            p.GAME_START, stage=self.world.stage.key, stocks=C.STOCKS,
            seconds=self.world.max_frames // C.TICK_RATE,
            roster=[{"pid": pl.id, "fighter": pl.fighter, "name": pl.name, "bot": pl.bot}
                    for pl in sorted(self.lobby.players.values(), key=lambda x: x.id)],
        )

    def back_to_lobby(self, notice: str = "") -> None:
        self.phase, self.world, self.reset_in = LOBBY, None, None
        self.notice = notice
        self.bots, self.queues = {}, {}
        for pl in [pl for pl in self.lobby.players.values() if not pl.connected]:
            self.lobby.leave(pl.id)
        self.lobby.reset_ready()
        self._lobby_dirty = True

    def tick(self) -> None:
        """Um passo da partida (chamado 60x por segundo)."""
        w = self.world
        if w is None:
            return
        inputs = {pid: q.pop() for pid, q in self.queues.items() if pid not in self.bots}
        for pid, bot in self.bots.items():
            inputs[pid] = bot.think(w)
        w.step(inputs)
        self.events.extend(w.events)
        if w.frame % C.SNAPSHOT_EVERY == 0 or w.over:
            snap = w.snapshot()
            snap["events"] = self.events
            self.events = []
            for pid, ws in self.clients.items():
                q = self.queues.get(pid)
                self._send([ws], p.encode(p.SNAPSHOT, **snap, ack=q.ack if q else None))
        if w.over:
            if self.reset_in is None:
                self.reset_in = RESET_DELAY
            self.reset_in -= C.TICK_DT
            if self.reset_in <= 0:
                self.back_to_lobby()

    # ------------------------------------------------------------------ conexões
    async def handler(self, ws: ServerConnection) -> None:
        try:
            hello = p.decode(await ws.recv())
        except (ConnectionClosed, ValueError):
            return
        if hello.get("t") != p.HELLO:
            await ws.close(reason="esperava hello")
            return
        if hello.get("version") != p.PROTOCOL_VERSION:
            await ws.send(p.encode(p.ERROR, reason="versão do jogo diferente da do servidor"))
            await ws.close()
            return
        if self.password is not None and not secrets.compare_digest(
                str(hello.get("password") or "").encode(), self.password.encode()):
            await ws.send(p.encode(p.ERROR, reason="senha incorreta"))
            await ws.close()
            return
        player = self._admit(ws, hello)
        if player is None:
            await ws.send(p.encode(p.ERROR, reason="sala cheia ou partida em andamento"))
            await ws.close()
            return
        try:
            async for raw in ws:
                try:
                    msg = p.decode(raw)
                    if msg["t"] == p.LEAVE:
                        break
                    if self.clients.get(player.id) is ws:
                        self._handle(player, msg)
                except (KeyError, TypeError, ValueError):
                    continue  # mensagem malformada: ignora
        except ConnectionClosed:
            pass
        finally:
            self._drop(ws)

    def _admit(self, ws: ServerConnection, hello: dict) -> Player | None:
        player = self.lobby.by_token(str(hello.get("token") or ""))
        if player is not None:
            old = self.clients.get(player.id)
            if old is not None and old is not ws:
                self.conn_player.pop(old, None)
                asyncio.ensure_future(old.close(reason="reconectou em outra conexão"))
            log.info("%s reconectou (id=%d)", player.name, player.id)
        elif self.phase == LOBBY:
            player = self.lobby.join(str(hello.get("name", "")), secrets.token_hex(8))
            if player is None:
                return None
            log.info("%s entrou na sala (id=%d)", player.name, player.id)
        else:
            return None
        player.connected = True
        self.clients[player.id] = ws
        self.conn_player[ws] = player.id
        self._send([ws], p.encode(p.WELCOME, player_id=player.id, token=player.token,
                                  phase=self.phase))
        if self.phase == GAME and self.world is not None:
            self.bots.pop(player.id, None)  # volta a controlar o próprio lutador
            q = self.queues.setdefault(player.id, InputQueue())
            q.reset()
            self._send([ws], self._game_start_msg())
        self._lobby_dirty = True
        return player

    def _drop(self, ws: ServerConnection) -> None:
        pid = self.conn_player.pop(ws, None)
        if pid is None or self.clients.get(pid) is not ws:
            return
        self.clients.pop(pid, None)
        player = self.lobby.players.get(pid)
        if player is None:
            return
        if self.phase == LOBBY:
            self.lobby.leave(pid)
            log.info("%s saiu da sala", player.name)
        else:
            player.connected = False
            if self.world is not None:
                self.bots[pid] = BotBrain(pid, self.lobby.bot_level, seed=pid)
            log.info("%s caiu da partida; um bot assume até voltar", player.name)
            if not self.clients:
                log.info("todos os humanos saíram; voltando à sala")
                self.back_to_lobby()
        self._lobby_dirty = True

    def _handle(self, player: Player, msg: dict) -> None:
        t = msg["t"]
        if t == p.INPUT:
            q = self.queues.get(player.id)
            if q is not None and self.phase == GAME:
                entries = [(int(s), int(b)) for s, b in msg["inputs"]][-C.INPUT_REDUNDANCY * 2:]
                if self.fake_lag and self._loop is not None:
                    self._loop.call_later(self.fake_lag / 2, q.push, entries)
                else:
                    q.push(entries)
            return
        if self.phase != LOBBY:
            return
        lb, pid = self.lobby, player.id
        changed = False
        if t == p.PICK:
            changed = lb.pick(pid, str(msg["fighter"]))
        elif t == p.READY:
            changed = lb.set_ready(pid, bool(msg["ready"]))
        elif t == p.STAGE:
            changed = lb.set_stage(pid, str(msg["stage"]))
        elif t == p.BOTS:
            changed = lb.set_bot_level(pid, str(msg["level"]))
        elif t == p.ADD_BOT:
            changed = lb.add_bot(pid) is not None
        elif t == p.REMOVE_BOT:
            changed = lb.remove_bot(pid)
        elif t == p.START and lb.can_start(pid):
            self.start_game()
            changed = True
        self._lobby_dirty |= changed

    # ------------------------------------------------------------------ laço
    async def tick_loop(self) -> None:
        loop = asyncio.get_running_loop()
        next_time = loop.time()
        while True:
            if self.phase == GAME:
                self.tick()
            if self._lobby_dirty and self.clients:
                self._lobby_dirty = False
                self._broadcast_lobby()
            next_time += C.TICK_DT
            delay = next_time - loop.time()
            if delay < -0.25:  # muito atrasado (PC travou): não tenta recuperar tudo
                next_time = loop.time()
                delay = 0
            await asyncio.sleep(max(0.0, delay))

    async def run(self, host: str, port: int, ready: asyncio.Event | None = None) -> None:
        self._loop = asyncio.get_running_loop()
        web.info_provider = self.info
        async with serve(self.handler, host, port, compression=None,
                         process_request=web.process_request):
            log.info("servidor em %s:%d%s", host, port, " (com senha)" if self.password else "")
            if ready:
                ready.set()
            await self.tick_loop()
