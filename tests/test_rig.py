"""A pose do esqueleto é calculável (sem NaN) em todos os estados e frames de todos os golpes."""

import math

from client.rig import pose
from shared.content import fighters
from tests.helpers import make_world


def _ok(p) -> bool:
    vals = [p.crouch, p.lean, p.weapon, p.lift, *p.legs, *p.arms]
    return all(math.isfinite(v) for v in vals)


def test_pose_for_every_move_frame_and_state():
    for key, fd in fighters().items():
        w = make_world(key, "toro")
        f = w.fighters[0]
        for st in ("idle", "run", "air", "hitstun", "dodge", "land", "ledge"):
            f.state = st
            for fr in (0, 7, 33):
                assert _ok(pose(f, fr))
        f.state = "attack"
        for m in fd.moves.values():
            f.move = m
            for grounded in (True, False):
                f.grounded = grounded
                for mf in range(m.total):
                    f.move_frame = mf
                    f.charging = mf == m.startup - 1 and m.charge > 0
                    assert _ok(pose(f, mf))
