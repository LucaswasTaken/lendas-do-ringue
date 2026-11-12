import random

from server.bots import BotBrain
from shared import constants as C
from tests.helpers import I, make_world, run


def _random_inputs(seed: int, frames: int, players: int):
    rng = random.Random(seed)
    buttons = [I.LEFT, I.RIGHT, I.UP, I.DOWN, I.JUMP, I.LIGHT, I.HEAVY, I.DODGE]
    seq = []
    for _ in range(frames):
        seq.append({p: sum(b for b in buttons if rng.random() < 0.15) for p in range(players)})
    return seq


def test_determinism_same_inputs_same_state():
    seq = _random_inputs(42, 1500, 3)
    snaps = []
    for _ in range(2):
        w = make_world("ravena", "toro", "lince")
        for inp in seq:
            w.step(inp)
        snap = w.snapshot()
        snap.pop("events")
        snaps.append(snap)
    assert snaps[0] == snaps[1]


def test_snapshot_roundtrip_continues_identically():
    seq = _random_inputs(7, 900, 2)
    a = make_world("ravena", "lince")
    for inp in seq[:400]:
        a.step(inp)
    b = make_world("ravena", "lince")
    b.apply_snapshot(a.snapshot())
    for inp in seq[400:]:
        a.step(inp)
        b.step(inp)
    sa, sb = a.snapshot(), b.snapshot()
    sa.pop("events")
    sb.pop("events")
    assert sa == sb


def test_falling_off_stage_loses_stock():
    w = make_world("ravena", "toro")
    f = w.fighters[0]
    f.x, f.y = -1000, 0
    run(w, 120)
    assert f.stocks == 2 and f.falls == 1


def test_last_team_standing_wins():
    w = make_world("ravena", "toro", stocks=1)
    w.fighters[1].x = 2000
    run(w, 2)
    assert w.over and w.winner == 0


def test_timeout_picks_most_stocks():
    w = make_world("ravena", "toro", seconds=1)
    w.fighters[1].stocks = 1
    run(w, C.TICK_RATE + 1)
    assert w.over and w.winner == 0


def test_bot_match_finishes():
    w = make_world("ravena", "toro", "lince", "ondina", stocks=2, seconds=240)
    bots = [BotBrain(p, "dificil", seed=1) for p in range(4)]
    frames = 0
    while not w.over and frames < 240 * C.TICK_RATE:
        w.step({b.pid: b.think(w) for b in bots})
        frames += 1
    assert w.over
    assert sum(f.kos + f.falls for f in w.fighters.values()) > 0
