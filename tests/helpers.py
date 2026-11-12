from shared import inputs as I
from shared.content import fighters, stages
from shared.sim import World


def make_world(*keys: str, stage: str = "coliseu", **kw) -> World:
    roster = [(i, fighters()[k]) for i, k in enumerate(keys)]
    return World(stages()[stage], roster, **kw)


def run(world: World, frames: int, inputs: dict[int, int] | None = None) -> None:
    for _ in range(frames):
        world.step(inputs or {})


def settle(world: World) -> None:
    """Deixa todos caírem e pousarem."""
    run(world, 90)


def press(world: World, pid: int, bits: int, hold: int = 1) -> None:
    """Aperta `bits` por `hold` frames e solta (1 frame)."""
    for _ in range(hold):
        world.step({pid: bits})
    world.step({})


__all__ = ["I", "make_world", "run", "settle", "press"]
