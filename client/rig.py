"""Lutador desenhado como um esqueleto 2D (cinemática direta), sem sprites.

`pose()` é pura: a partir do estado do lutador calcula os ângulos dos membros.
Ângulos em graus no "espaço do lutador": 0 = para a frente, 90 = cima, -90 = baixo.
Golpes miram o braço no centro da 1ª hitbox, então qualquer golpe novo no YAML já anima.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import arcade

from shared.sim import Fighter

HEAVY_PREFIX = ("heavy_", "air_heavy", "recovery")


@dataclass
class Pose:
    crouch: float = 0.0  # 0..1 abaixa o quadril
    lean: float = 0.0  # inclinação do tronco para a frente (graus)
    legs: tuple[float, float, float, float] = (-95, -90, -85, -90)  # coxa/canela frente, trás
    arms: tuple[float, float, float, float] = (-100, -80, -80, -95)  # braço/antebraço frente, trás
    weapon: float = 0.0  # ângulo extra da arma em relação ao antebraço
    lift: float = 0.0  # sobe o corpo (px relativos à altura) — ex.: pendurado


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_t(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(_lerp(x, y, t) for x, y in zip(a, b, strict=True))


REST_ARMS = (-100.0, -70.0, -80.0, -100.0)


def pose(f: Fighter, frame: int) -> Pose:
    st = f.state
    h = f.fdef.height
    if st == "ledge":
        return Pose(legs=(-100, -95, -80, -90), arms=(78, 85, 95, 90), lift=0.0)
    if st == "hitstun":
        wob = math.sin(frame * 0.9) * 25
        return Pose(lean=-28, legs=(-60 + wob, -120, -135, -100 - wob),
                    arms=(130 + wob, 160, 60 - wob, 30), weapon=40)
    if st == "dodge":
        return Pose(crouch=0.35, lean=25, legs=(-60, -110, -120, -80),
                    arms=(-60, -20, -120, -90))
    if st == "land":
        return Pose(crouch=0.4, lean=12, legs=(-50, -115, -125, -70))
    if st == "attack" and f.move is not None:
        return _attack_pose(f, h, frame)
    if not f.grounded:
        if f.vy > 0:
            return Pose(legs=(-35, -105, -70, -125), arms=(-40, -10, -140, -110), lean=5)
        return Pose(legs=(-100, -95, -78, -100), arms=(-20, 10, -150, -130))
    if st == "run" or abs(f.vx) > 60:
        p = frame * 0.32 * f.fdef.speed
        s = math.sin(p)
        ft = -90 + 38 * s
        bt = -90 - 38 * s
        return Pose(lean=14, legs=(ft, ft - 25 - 25 * max(0.0, -s), bt, bt - 25 - 25 * max(0.0, s)),
                    arms=(-90 - 40 * s, -60 - 40 * s, -90 + 40 * s, -60 + 40 * s), weapon=80)
    breath = math.sin(frame * 0.08) * 3
    return Pose(crouch=0.04 + breath * 0.004, legs=(-100, -88, -78, -92),
                arms=(-105 + breath, -55, -75 - breath, -100), weapon=105)


def _attack_pose(f: Fighter, h: float, frame: int) -> Pose:
    m = f.move
    key = m.key
    hb = m.hitboxes[0]
    shoulder_y = h * 0.72
    aim = math.degrees(math.atan2(hb.y - shoulder_y, max(hb.x, 1.0)))
    heavy = key.startswith(HEAVY_PREFIX)
    windup = aim + (150 if heavy else 105)
    mf = f.move_frame
    if mf < m.startup:
        t = (mf + 1) / m.startup
        a = _lerp(REST_ARMS[0], windup, min(1.0, t * 1.4))
        if f.charging:
            a = windup + math.sin(frame * 1.7) * 4
        arm = (a, a + 25, -60, -100)
        weapon = 30
    elif mf < m.startup + m.active:
        arm = (aim, aim, -150, -120)
        weapon = 0
    else:
        t = (mf - m.startup - m.active) / max(1, m.recovery)
        a = _lerp(aim - 25, REST_ARMS[0], t)
        arm = (a, _lerp(aim - 10, REST_ARMS[1], t), -110, -100)
        weapon = 0
    legs = (-75, -100, -120, -85)  # base aberta
    crouch, lean = 0.05, 10
    if key.endswith("_down") and f.grounded:
        crouch, lean, legs = 0.4, 20, (-40, -120, -140, -60)
    elif key in ("air_down", "air_heavy_down"):
        legs, lean = (-95, -95, -85, -85), -5
    elif not f.grounded:
        legs = (-40, -110, -80, -120)
    if key == "recovery":
        lean = -5
    return Pose(crouch=crouch, lean=lean, legs=legs, arms=arm, weapon=weapon)


# --------------------------------------------------------------------------- desenho
def _pt(ox: float, oy: float, ang: float, length: float, facing: int) -> tuple[float, float]:
    r = math.radians(ang)
    return ox + math.cos(r) * length * facing, oy + math.sin(r) * length


def _shade(c, k: float):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def _limb(a, b, width: float, color, alpha: int) -> None:
    arcade.draw_line(a[0], a[1], b[0], b[1], (20, 20, 30, alpha), width + 4)
    arcade.draw_line(a[0], a[1], b[0], b[1], (*color, alpha), width)
    arcade.draw_circle_filled(b[0], b[1], width / 2, (*color, alpha))


def draw(f: Fighter, x: float, y: float, frame: int, alpha: int = 255,
         tint: tuple[int, int, int] | None = None) -> None:
    fd = f.fdef
    h = fd.height
    fc = f.facing
    p = pose(f, frame)
    color = tint or fd.color
    back = _shade(color, 0.68)
    lw = max(6.0, h * 0.085)

    thigh, shin = h * 0.25, h * 0.24
    hip = (x, y + h * (0.47 - 0.2 * p.crouch) + p.lift * h)
    torso_ang = 90 - p.lean
    neck = _pt(*hip, torso_ang, h * 0.31, fc)
    shoulder = _pt(*hip, torso_ang, h * 0.27, fc)
    head = _pt(*hip, torso_ang, h * 0.43, fc)
    upper, fore = h * 0.17, h * 0.16

    def leg(t_ang, s_ang, col):
        knee = _pt(*hip, t_ang, thigh, fc)
        foot = _pt(*knee, s_ang, shin, fc)
        _limb(hip, knee, lw, col, alpha)
        _limb(knee, foot, lw * 0.9, col, alpha)

    def arm(u_ang, f_ang, col, with_weapon):
        elbow = _pt(*shoulder, u_ang, upper, fc)
        hand = _pt(*elbow, f_ang, fore, fc)
        if with_weapon:
            _weapon(fd.weapon, hand, f_ang + p.weapon, h, fc, fd.accent, alpha)
        _limb(shoulder, elbow, lw * 0.8, col, alpha)
        _limb(elbow, hand, lw * 0.75, col, alpha)

    lt_f, ls_f, lt_b, ls_b = p.legs
    au_f, af_f, au_b, af_b = p.arms
    arm(au_b, af_b, back, False)
    leg(lt_b, ls_b, back)
    # tronco
    arcade.draw_line(hip[0], hip[1], neck[0], neck[1], (20, 20, 30, alpha), lw * 1.7 + 4)
    arcade.draw_line(hip[0], hip[1], neck[0], neck[1], (*color, alpha), lw * 1.7)
    belt = _pt(*hip, torso_ang, h * 0.03, fc)
    arcade.draw_circle_filled(belt[0], belt[1], lw * 0.7, (*_shade(fd.accent, 0.8), alpha))
    leg(lt_f, ls_f, color)
    # cabeça
    r = h * 0.105
    arcade.draw_circle_filled(head[0], head[1], r + 2, (20, 20, 30, alpha))
    arcade.draw_circle_filled(head[0], head[1], r, (240, 210, 180, alpha))
    arcade.draw_arc_filled(head[0], head[1] + r * 0.15, r * 2.2, r * 2.0, (*fd.hair, alpha),
                           0, 180)
    ex = head[0] + fc * r * 0.45
    arcade.draw_circle_filled(ex, head[1], max(2.0, r * 0.18), (20, 20, 30, alpha))
    arm(au_f, af_f, color, True)


def _weapon(kind: str, hand, ang: float, h: float, fc: int, accent, alpha: int) -> None:
    metal = (205, 212, 228, alpha)
    wood = (120, 80, 50, alpha)
    dark = (20, 20, 30, alpha)
    if kind == "sword":
        tip = _pt(*hand, ang, h * 0.5, fc)
        guard_a = _pt(*hand, ang + 90, h * 0.07, fc)
        guard_b = _pt(*hand, ang - 90, h * 0.07, fc)
        arcade.draw_line(*hand, *tip, dark, 9)
        arcade.draw_line(*hand, *tip, metal, 5)
        arcade.draw_line(*guard_a, *guard_b, (*accent, alpha), 5)
    elif kind == "hammer":
        end = _pt(*hand, ang, h * 0.48, fc)
        start = _pt(*hand, ang, -h * 0.08, fc)
        arcade.draw_line(*start, *end, dark, 9)
        arcade.draw_line(*start, *end, wood, 5)
        a = _pt(*end, ang + 90, h * 0.13, fc)
        b = _pt(*end, ang - 90, h * 0.13, fc)
        arcade.draw_line(*a, *b, dark, h * 0.17 + 4)
        arcade.draw_line(*a, *b, (*accent, alpha), h * 0.17)
    elif kind == "spear":
        start = _pt(*hand, ang, -h * 0.3, fc)
        end = _pt(*hand, ang, h * 0.62, fc)
        arcade.draw_line(*start, *end, dark, 8)
        arcade.draw_line(*start, *end, wood, 4)
        tip = _pt(*end, ang, h * 0.16, fc)
        sa = _pt(*end, ang + 90, h * 0.05, fc)
        sb = _pt(*end, ang - 90, h * 0.05, fc)
        arcade.draw_triangle_filled(*tip, *sa, *sb, metal)
    else:  # claws
        for off in (-18, 0, 18):
            tip = _pt(*hand, ang + off, h * 0.17, fc)
            arcade.draw_line(*hand, *tip, dark, 6)
            arcade.draw_line(*hand, *tip, (*accent, alpha), 3)
