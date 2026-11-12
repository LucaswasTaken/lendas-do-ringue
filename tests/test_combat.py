from shared import combat
from shared.content import HitboxDef
from tests.helpers import I, make_world, press, run, settle

HB = HitboxDef(x=50, y=50, w=40, h=40, dmg=10, angle=45, base=300, growth=10)


def test_knockback_grows_with_damage_and_shrinks_with_weight():
    assert combat.knockback(HB, 100, 1.0) > combat.knockback(HB, 10, 1.0)
    assert combat.knockback(HB, 100, 1.3) < combat.knockback(HB, 100, 1.0)


def test_hitbox_is_mirrored_by_facing():
    r = combat.hitbox_rect(HB, 0, 0, 1)
    l_ = combat.hitbox_rect(HB, 0, 0, -1)
    assert r[0] > 0 and l_[1] < 0


def test_di_rotates_launch_at_most_limit():
    vx, vy = combat.launch_vector(0, 1000, 1, 0, 1)  # segura para cima
    import math
    ang = math.degrees(math.atan2(vy, vx))
    assert 14.9 < ang < 15.1


def _face_off(dist=80):
    w = make_world("ravena", "toro")
    settle(w)
    a, b = w.fighters[0], w.fighters[1]
    a.x, b.x = 0, dist
    a.facing = 1
    return w, a, b


def test_light_side_hits_adds_damage_and_launches():
    w, a, b = _face_off()
    press(w, 0, I.LIGHT | I.RIGHT)
    run(w, 10)
    assert b.damage == 9
    assert b.vx > 0 or b.x > 80
    assert b.last_hit_by == 0


def test_one_hit_per_attack_and_invulnerable_dodge():
    w, a, b = _face_off()
    press(w, 0, I.LIGHT | I.RIGHT)
    run(w, 25)
    assert b.damage == 9  # só um acerto mesmo com vários frames ativos
    w2, a2, b2 = _face_off()
    press(w2, 1, I.DODGE)  # esquiva parada: invulnerável
    press(w2, 0, I.LIGHT)
    run(w2, 10)
    assert b2.damage == 0


def test_charged_heavy_does_more_damage():
    w, a, b = _face_off(dist=110)
    press(w, 0, I.HEAVY | I.RIGHT, hold=1)
    run(w, 40)
    quick = b.damage
    w2, a2, b2 = _face_off(dist=110)
    press(w2, 0, I.HEAVY | I.RIGHT, hold=60)
    run(w2, 40)
    assert quick > 0 and b2.damage > quick


def test_high_damage_strong_hit_kos_and_respawns():
    w, a, b = _face_off(dist=110)
    b.damage = 200
    press(w, 0, I.HEAVY | I.RIGHT, hold=45)
    run(w, 200)
    assert b.stocks == 2 and a.kos == 1
    run(w, 100)
    assert b.alive and b.damage == 0


def test_low_damage_hit_does_not_ko():
    w, a, b = _face_off(dist=110)
    press(w, 0, I.HEAVY | I.RIGHT)
    run(w, 200)
    assert b.stocks == 3
