from shared import constants as C
from shared.content import Platform
from shared.physics import move_body
from tests.helpers import I, make_world, press, run, settle

FLOOR = (Platform(-500, -100, 1000, 100),)
SOFT = (Platform(-100, 200, 200, 16, soft=True),)


def test_fast_fall_does_not_tunnel_through_floor():
    x, y, vx, vy, res = move_body(0, 10, 0, -50_000, 25, 100, C.TICK_DT, FLOOR, False)
    assert res.landed and y == 0 and vy == 0


def test_soft_platform_passes_from_below_and_holds_from_above():
    _, y, _, _, res = move_body(0, 190, 0, 900, 25, 100, C.TICK_DT, SOFT, False)
    assert not res.hit_ceiling and y > 190
    _, y, _, _, res = move_body(0, 220, 0, -900, 25, 100, C.TICK_DT, SOFT, False)
    assert res.landed and y == 216
    _, y, _, _, res = move_body(0, 220, 0, -900, 25, 100, C.TICK_DT, SOFT, True)
    assert not res.landed


def test_solid_wall_blocks_horizontal():
    wall = (Platform(100, 0, 50, 300),)
    x, _, vx, _, res = move_body(60, 10, 5000, 0, 25, 100, C.TICK_DT, wall, False)
    assert res.hit_wall and x == 75 and vx == 0


def test_fighter_lands_and_jumps():
    w = make_world("ravena", "toro")
    settle(w)
    f = w.fighters[0]
    assert f.grounded and f.y == 0 and f.state == "idle"
    press(w, 0, I.JUMP)
    assert not f.grounded and f.y > 0
    run(w, 10)
    peak_before = f.y
    press(w, 0, I.JUMP)  # pulo aéreo
    assert f.jumps_left == f.fdef.air_jumps - 1
    run(w, 6)
    assert f.y > peak_before


def test_drop_through_soft_platform():
    w = make_world("ravena", "toro")
    f = w.fighters[0]
    f.x, f.y = -275, 300  # acima da plataforma fina da esquerda
    settle(w)
    assert f.grounded and f.y == 226
    press(w, 0, I.DOWN)
    run(w, 40)
    assert f.grounded and f.y == 0


def _hang_right_ledge():
    w = make_world("ravena", "toro")
    settle(w)
    f = w.fighters[0]
    # cai rente à quina direita do Coliseu (x = 520, topo = 0)
    f.x, f.y, f.vx, f.vy = 520 + f.half_w + 5, 10, 0.0, 0.0
    f.grounded, f.state = False, "air"
    run(w, 30)
    return w, f


def test_grabs_ledge_and_climbs():
    w, f = _hang_right_ledge()
    assert f.state == "ledge" and f.ledge_side == 1
    assert f.jumps_left == f.fdef.air_jumps and f.invuln > 0
    press(w, 0, I.UP)
    assert f.grounded and f.state == "idle" and f.x < 520 and f.y == 0


def test_ledge_jump_and_drop():
    w, f = _hang_right_ledge()
    press(w, 0, I.JUMP)
    assert f.state == "air" and f.vy > 0
    w2, f2 = _hang_right_ledge()
    press(w2, 0, I.DOWN)
    assert f2.state == "air"
    run(w2, 20)
    assert f2.state == "air" and f2.y < -50  # não reagarra na hora


def test_ledge_releases_after_timeout():
    w, f = _hang_right_ledge()
    run(w, C.LEDGE_MAX + 5)
    assert f.state != "ledge"


def test_running_respects_speed_and_turns():
    w = make_world("ravena", "toro")
    settle(w)
    f = w.fighters[0]
    run(w, 30, {0: I.RIGHT})
    assert f.facing == 1 and abs(f.vx - C.RUN_SPEED * f.fdef.speed) < 1
    run(w, 30, {0: I.LEFT})
    assert f.facing == -1 and f.vx < 0
