"""Input de um jogador num tick: bitmask de botões. É o que trafega na rede e alimenta a sim."""

LEFT = 1 << 0
RIGHT = 1 << 1
UP = 1 << 2
DOWN = 1 << 3
JUMP = 1 << 4
LIGHT = 1 << 5
HEAVY = 1 << 6
DODGE = 1 << 7
THROW = 1 << 8  # reservado para armas (pós-MVP)

BUFFERED = (JUMP, LIGHT, HEAVY, DODGE)


def axis_x(bits: int) -> int:
    return (1 if bits & RIGHT else 0) - (1 if bits & LEFT else 0)


def axis_y(bits: int) -> int:
    return (1 if bits & UP else 0) - (1 if bits & DOWN else 0)
