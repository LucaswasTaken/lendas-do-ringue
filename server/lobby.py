"""Sala de espera: até 4 vagas (humanos + bots), escolha de lutador, pronto, anfitrião."""

from __future__ import annotations

from dataclasses import dataclass

from shared.constants import MAX_PLAYERS

BOT_NAMES = ["Bot Ferro", "Bot Brasa", "Bot Vento", "Bot Rocha"]
BOT_LEVELS = ("facil", "medio", "dificil")


@dataclass
class Player:
    id: int
    name: str
    token: str
    fighter: str
    ready: bool = False
    bot: bool = False
    connected: bool = True


class Lobby:
    def __init__(self, fighter_keys: list[str], stage_keys: list[str]) -> None:
        self.fighter_keys = fighter_keys
        self.stage_keys = stage_keys
        self.stage = stage_keys[0]
        self.bot_level = "medio"
        self.players: dict[int, Player] = {}
        self.host_id: int | None = None

    def _free_slot(self) -> int | None:
        return next((i for i in range(MAX_PLAYERS) if i not in self.players), None)

    def humans(self) -> list[Player]:
        return [p for p in self.players.values() if not p.bot]

    def by_token(self, token: str) -> Player | None:
        if not token:
            return None
        return next((p for p in self.players.values() if p.token == token and not p.bot), None)

    def join(self, name: str, token: str) -> Player | None:
        slot = self._free_slot()
        if slot is None:
            return None
        name = (name or "").strip()[:16] or f"Jogador{slot + 1}"
        fighter = self.fighter_keys[slot % len(self.fighter_keys)]
        p = Player(slot, name, token, fighter)
        self.players[slot] = p
        if self.host_id is None:
            self.host_id = slot
        return p

    def leave(self, pid: int) -> None:
        self.players.pop(pid, None)
        if pid == self.host_id:
            hs = sorted(self.humans(), key=lambda p: p.id)
            self.host_id = hs[0].id if hs else None
        if self.host_id is None:
            self.players.clear()  # sem humanos a sala esvazia (tira os bots)

    def pick(self, pid: int, fighter: str) -> bool:
        p = self.players.get(pid)
        if p is None or fighter not in self.fighter_keys:
            return False
        p.fighter = fighter
        return True

    def set_ready(self, pid: int, ready: bool) -> bool:
        p = self.players.get(pid)
        if p is None:
            return False
        p.ready = ready
        return True

    def is_host(self, pid: int) -> bool:
        return pid == self.host_id

    def set_stage(self, pid: int, stage: str) -> bool:
        if not self.is_host(pid) or stage not in self.stage_keys:
            return False
        self.stage = stage
        return True

    def set_bot_level(self, pid: int, level: str) -> bool:
        if not self.is_host(pid) or level not in BOT_LEVELS:
            return False
        self.bot_level = level
        return True

    def add_bot(self, pid: int) -> Player | None:
        slot = self._free_slot()
        if not self.is_host(pid) or slot is None:
            return None
        used = {p.fighter for p in self.players.values()}
        fighter = next((k for k in self.fighter_keys if k not in used),
                       self.fighter_keys[slot % len(self.fighter_keys)])
        p = Player(slot, BOT_NAMES[slot % len(BOT_NAMES)], "", fighter, ready=True, bot=True)
        self.players[slot] = p
        return p

    def remove_bot(self, pid: int) -> bool:
        bots = sorted((p for p in self.players.values() if p.bot), key=lambda p: p.id)
        if not self.is_host(pid) or not bots:
            return False
        del self.players[bots[-1].id]
        return True

    def can_start(self, pid: int | None = None) -> bool:
        if pid is not None and not self.is_host(pid):
            return False
        if len(self.players) < 2:
            return False
        return all(p.ready or p.bot or p.id == self.host_id for p in self.players.values())

    def reset_ready(self) -> None:
        for p in self.players.values():
            p.ready = p.bot

    def state(self, phase: str) -> dict:
        return {
            "phase": phase,
            "host": self.host_id,
            "stage": self.stage,
            "bot_level": self.bot_level,
            "can_start": self.can_start(),
            "players": [
                {"id": p.id, "name": p.name, "fighter": p.fighter, "ready": p.ready,
                 "bot": p.bot, "connected": p.connected}
                for p in sorted(self.players.values(), key=lambda p: p.id)
            ],
        }
