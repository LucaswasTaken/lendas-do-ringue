"""Quem faz a partida andar: local (sim inteira aqui) ou online (predição + snapshots).

A GameView só conhece esta interface:
    world            World usado para desenhar
    tick() -> list   avança 1 frame (60 Hz) e devolve eventos para efeitos
    label(pid)       "P1", "CPU3", nome do jogador...
    offset(pid)      correção visual suave (só online)
    finished         True quando deve sair da tela de jogo
"""

from __future__ import annotations

import math
from collections import deque

from client.input import GamepadSource, KeyboardSource, open_gamepads
from server.bots import BotBrain
from shared import constants as C
from shared.content import fighters, stages
from shared.sim import World, apply_state

PLAYER_TAGS = ["P1", "P2", "P3", "P4"]


class LocalDriver:
    online = False

    def __init__(self, setup) -> None:
        self.setup = setup
        roster = [(i, fighters()[k]) for i, k in enumerate(setup.picks)]
        self.world = World(stages()[setup.stage], roster)
        pads = open_gamepads()
        self.sources: dict[int, list] = {}
        for pid in range(setup.humans):
            srcs: list = [KeyboardSource(f"p{pid + 1}")]
            if pid < len(pads):
                srcs.append(GamepadSource(pads[pid]))
            self.sources[pid] = srcs
        self.bots = [BotBrain(pid, setup.difficulty, seed=pid)
                     for pid in range(setup.humans, setup.humans + setup.bots)]
        self.finished = False

    def tick(self) -> list[dict]:
        w = self.world
        inputs = {pid: _combine(srcs) for pid, srcs in self.sources.items()}
        for b in self.bots:
            inputs[b.pid] = b.think(w)
        w.step(inputs)
        return w.events

    def label(self, pid: int) -> str:
        return PLAYER_TAGS[pid] if pid < self.setup.humans else f"CPU{pid + 1}"

    def is_bot(self, pid: int) -> bool:
        return pid >= self.setup.humans

    def offset(self, pid: int) -> tuple[float, float]:
        return 0.0, 0.0

    def close(self) -> None:
        pass


class NetDriver:
    """Partida online.

    - O próprio lutador é previsto: cada frame aplica o input local na hora (step_one) e
      guarda o input como pendente. Quando chega um snapshot com `ack`, copia o estado do
      servidor, descarta os inputs já confirmados e re-simula os pendentes.
    - Os outros lutadores são desenhados interpolando snapshots, INTERP_FRAMES no passado.
    """

    online = True
    PREDICTED_EVENTS = ("jump", "dodge", "attack")

    def __init__(self, net, sources: list | None = None) -> None:
        self.net = net
        if sources is None:
            pads = open_gamepads()
            sources = [KeyboardSource("p1"), *(GamepadSource(p) for p in pads[:1])]
        self.sources = sources
        gs = net.game_start
        self.gen = net.game_gen
        self.roster = {r["pid"]: r for r in gs["roster"]}
        self.world = World(stages()[gs["stage"]],
                           [(r["pid"], fighters()[r["fighter"]]) for r in gs["roster"]],
                           stocks=gs["stocks"], seconds=gs["seconds"])
        self.me = net.player_id
        self.seq = 0
        self.pending: deque[tuple[int, int]] = deque()
        self.snaps: deque[dict] = deque(maxlen=40)
        self.since_latest = 0
        self.err = [0.0, 0.0]
        self.finished = False
        self.corrections = 0  # quantas vezes a predição errou feio (diagnóstico)

    # ------------------------------------------------------------------ ciclo
    def tick(self) -> list[dict]:
        events = self._drain()
        net = self.net
        lost = not net.connected and not net.reconnecting
        if lost or net.phase == "lobby" or net.game_gen != self.gen:
            self.finished = True
            return events
        if not net.connected:  # reconectando: segura o lutador parado até voltar
            return events
        bits = _combine(self.sources)
        self.seq += 1
        self.pending.append((self.seq, bits))
        while len(self.pending) > 120:  # servidor sumiu: não deixa crescer sem limite
            self.pending.popleft()
        self.net.send_inputs(list(self.pending)[-C.INPUT_REDUNDANCY:])
        if self.me in self.world.fighters:
            self.world.events = []
            self.world.step_one(self.me, bits)
            events += [e for e in self.world.events if e["e"] in self.PREDICTED_EVENTS]
        self.since_latest += 1
        self._place_others()
        self.err[0] *= 0.85
        self.err[1] *= 0.85
        return events

    def _drain(self) -> list[dict]:
        events: list[dict] = []
        while self.net.snapshots:
            snap = self.net.snapshots.popleft()
            self.snaps.append(snap)
            self.since_latest = 0
            for e in snap.get("events", ()):
                # os eventos do próprio lutador que a predição já mostrou não repetem
                if e["e"] in self.PREDICTED_EVENTS and e.get("p") == self.me:
                    continue
                events.append(e)
            self._reconcile(snap)
        return events

    def _reconcile(self, snap: dict) -> None:
        w = self.world
        w.frame, w.over, w.winner = snap["f"], snap["over"], snap["winner"]
        mine = next((s for s in snap["fighters"] if s["pid"] == self.me), None)
        if mine is None:
            return
        f = w.fighters[self.me]
        before = (f.x, f.y)
        ack = snap.get("ack")
        if ack is not None:
            while self.pending and self.pending[0][0] <= ack:
                self.pending.popleft()
        apply_state(f, mine)
        w.events = []
        for _, bits in self.pending:
            w.step_one(self.me, bits)
        w.events = []
        dx, dy = before[0] - f.x, before[1] - f.y
        if math.hypot(dx, dy) < 160:
            self.err[0] += dx
            self.err[1] += dy
        else:
            self.err = [0.0, 0.0]
        if math.hypot(dx, dy) > 4:
            self.corrections += 1

    def _place_others(self) -> None:
        if not self.snaps:
            return
        snaps = self.snaps
        render_f = snaps[-1]["f"] + self.since_latest - C.INTERP_FRAMES
        i = next((k for k in range(len(snaps) - 1, -1, -1) if snaps[k]["f"] <= render_f), None)
        if i is None:  # ainda não há snapshot velho o bastante
            a = b = snaps[0]
        elif i == len(snaps) - 1:  # snapshots atrasaram: segura no último
            a = b = snaps[-1]
        else:
            a, b = snaps[i], snaps[i + 1]
        t = 0.0
        if b["f"] > a["f"]:
            t = max(0.0, min(1.0, (render_f - a["f"]) / (b["f"] - a["f"])))
        b_by_pid = {s["pid"]: s for s in b["fighters"]}
        for sa in a["fighters"]:
            pid = sa["pid"]
            if pid == self.me:
                continue
            sb = b_by_pid.get(pid, sa)
            f = self.world.fighters[pid]
            apply_state(f, sb if t > 0.5 else sa)
            # só interpola posição se não houve teleporte (KO/respawn) entre os dois
            if abs(sb["x"] - sa["x"]) + abs(sb["y"] - sa["y"]) < 400:
                f.x = sa["x"] + (sb["x"] - sa["x"]) * t
                f.y = sa["y"] + (sb["y"] - sa["y"]) * t

    # ------------------------------------------------------------------ desenho
    def label(self, pid: int) -> str:
        r = self.roster.get(pid, {})
        name = r.get("name", f"P{pid + 1}")
        return f"{name} (você)" if pid == self.me else name

    def is_bot(self, pid: int) -> bool:
        return bool(self.roster.get(pid, {}).get("bot"))

    def offset(self, pid: int) -> tuple[float, float]:
        return (self.err[0], self.err[1]) if pid == self.me else (0.0, 0.0)

    def close(self) -> None:
        pass


def _combine(srcs: list) -> int:
    bits = 0
    for s in srcs:
        bits |= s.bits()
    return bits
