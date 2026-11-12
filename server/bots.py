"""Bots: geram o mesmo bitmask de input que um jogador humano."""

from __future__ import annotations

import random

from shared import inputs as I
from shared.sim import Fighter, World

# dificuldade -> (frames entre decisões, chance de atacar no alcance, chance de esquivar)
DIFFICULTY = {
    "facil": (14, 0.35, 0.05),
    "medio": (8, 0.6, 0.15),
    "dificil": (4, 0.85, 0.3),
}


class BotBrain:
    def __init__(self, pid: int, difficulty: str = "medio", seed: int = 0) -> None:
        self.pid = pid
        self.react, self.aggro, self.evade = DIFFICULTY[difficulty]
        self.rng = random.Random(seed * 7919 + pid)
        self.bits = 0
        self.cooldown = 0
        self.last = 0

    def think(self, world: World) -> int:
        me = world.fighters[self.pid]
        if not me.alive:
            return 0
        self.cooldown -= 1
        # A recuperação de borda é verificada todo frame (sem atraso de reação).
        bits = self._recover(world, me)
        if bits is None:
            if self.cooldown <= 0:
                self.cooldown = self.react
                bits = self._decide(world, me)
            else:
                bits = self.bits
        # Botões de ação só contam na borda: se já estavam apertados no frame anterior, solta.
        action = I.JUMP | I.LIGHT | I.HEAVY | I.DODGE
        out = bits & ~action if self.last & action else bits
        self.bits = bits & ~action  # entre decisões continua segurando só a direção
        self.last = out
        return out

    def _main_platform(self, world: World):
        return max(world.stage.platforms, key=lambda p: p.w)

    def _recover(self, world: World, me: Fighter) -> int | None:
        if me.state == "ledge":
            return I.UP  # sobe da borda
        main = self._main_platform(world)
        off_x = me.x < main.x - 10 or me.x > main.right + 10
        below = me.y < main.top - 10
        if not (off_x or below) or me.grounded:
            return None
        if me.state not in ("air", "attack", "dodge"):
            return None
        toward = I.RIGHT if me.x < (main.x + main.right) / 2 else I.LEFT
        bits = toward
        if me.vy < 0:
            if me.jumps_left > 0:
                bits |= I.JUMP
            elif not me.recovery_used and me.state == "air":
                bits |= I.HEAVY | I.UP
        return bits

    def _target(self, world: World, me: Fighter) -> Fighter | None:
        foes = [f for f in world.fighters.values() if f.team != me.team and f.alive]
        if not foes:
            return None
        return min(foes, key=lambda f: abs(f.x - me.x) + abs(f.y - me.y))

    def _decide(self, world: World, me: Fighter) -> int:
        tgt = self._target(world, me)
        if tgt is None:
            return 0
        dx, dy = tgt.x - me.x, tgt.y - me.y
        toward = I.RIGHT if dx > 0 else I.LEFT
        r = self.rng.random()

        if tgt.state == "attack" and abs(dx) < 160 and abs(dy) < 120 and r < self.evade:
            return I.DODGE | (I.LEFT if dx > 0 else I.RIGHT)

        if abs(dx) < 150 and abs(dy) < 110 and r < self.aggro:
            finish = me.grounded and self.rng.random() < min(0.8, tgt.damage / 160)
            if dy > 70:
                return I.HEAVY if finish else I.LIGHT  # neutro: golpe para cima
            if finish:
                return I.HEAVY | toward
            if not me.grounded and dy < -60:
                return I.LIGHT | I.DOWN
            return I.LIGHT | toward

        bits = toward if abs(dx) > 90 else 0
        if dy > 150 and me.grounded and self.rng.random() < 0.5:
            bits |= I.JUMP
        if dy < -150 and me.grounded:
            bits |= I.DOWN  # desce da plataforma fina
        return bits
