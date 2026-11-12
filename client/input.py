"""Converte teclado/controle no bitmask de shared.inputs."""

from __future__ import annotations

import arcade

from shared import inputs as I

K = arcade.key

KEYMAPS: dict[str, dict[int, tuple[int, ...]]] = {
    "p1": {
        I.LEFT: (K.A,), I.RIGHT: (K.D,), I.UP: (K.W,), I.DOWN: (K.S,),
        I.JUMP: (K.SPACE,), I.LIGHT: (K.J,), I.HEAVY: (K.K,), I.DODGE: (K.L,),
    },
    "p2": {
        I.LEFT: (K.LEFT,), I.RIGHT: (K.RIGHT,), I.UP: (K.UP,), I.DOWN: (K.DOWN,),
        I.JUMP: (K.RSHIFT, K.NUM_0), I.LIGHT: (K.COMMA, K.NUM_1),
        I.HEAVY: (K.PERIOD, K.NUM_2), I.DODGE: (K.SLASH, K.NUM_3),
    },
}

CONTROLS_HELP = {
    "p1": "P1: WASD mover · Espaço pular · J leve · K forte (segure p/ carregar) · L esquiva",
    "p2": "P2: setas mover · Shift dir. pular · , leve · . forte · / esquiva",
}


HELD: set[int] = set()  # teclas seguradas agora (as Views atualizam)


class KeyboardSource:
    def __init__(self, keymap: str, held: set[int] | None = None) -> None:
        self.map = KEYMAPS[keymap]
        self.held = HELD if held is None else held

    def bits(self) -> int:
        out = 0
        for bit, keys in self.map.items():
            if any(k in self.held for k in keys):
                out |= bit
        return out


class GamepadSource:
    """Controle via pyglet: A pula, X leve, B/Y forte, LB/RB/gatilhos esquiva."""

    DEAD = 0.45

    def __init__(self, controller) -> None:
        self.c = controller

    def bits(self) -> int:
        c = self.c
        out = 0
        lx, ly = getattr(c, "leftx", 0.0), getattr(c, "lefty", 0.0)
        if lx < -self.DEAD or getattr(c, "dpleft", False):
            out |= I.LEFT
        if lx > self.DEAD or getattr(c, "dpright", False):
            out |= I.RIGHT
        if ly > self.DEAD or getattr(c, "dpup", False):
            out |= I.UP
        if ly < -self.DEAD or getattr(c, "dpdown", False):
            out |= I.DOWN
        if getattr(c, "a", False):
            out |= I.JUMP
        if getattr(c, "x", False):
            out |= I.LIGHT
        if getattr(c, "b", False) or getattr(c, "y", False):
            out |= I.HEAVY
        if (getattr(c, "leftshoulder", False) or getattr(c, "rightshoulder", False)
                or getattr(c, "lefttrigger", 0) > 0.5 or getattr(c, "righttrigger", 0) > 0.5):
            out |= I.DODGE
        return out


def open_gamepads() -> list:
    try:
        import pyglet

        pads = pyglet.input.get_controllers()
    except Exception:
        return []
    opened = []
    for p in pads:
        try:
            p.open()
            opened.append(p)
        except Exception:
            pass
    return opened
