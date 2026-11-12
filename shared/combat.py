"""Fórmulas de combate: hitboxes no mundo, knockback, hitstun e DI. Funções puras."""

from __future__ import annotations

import math

from shared import constants as C
from shared.content import HitboxDef

Rect = tuple[float, float, float, float]  # esquerda, direita, baixo, cima


def hitbox_rect(hb: HitboxDef, x: float, y: float, facing: int) -> Rect:
    cx = x + hb.x * facing
    cy = y + hb.y
    return (cx - hb.w / 2, cx + hb.w / 2, cy - hb.h / 2, cy + hb.h / 2)


def hurtbox_rect(x: float, y: float, w: float, h: float) -> Rect:
    return (x - w / 2, x + w / 2, y, y + h)


def overlaps(a: Rect, b: Rect) -> bool:
    return a[0] < b[1] and a[1] > b[0] and a[2] < b[3] and a[3] > b[2]


def hitbox_active(hb: HitboxDef, active_frame: int) -> bool:
    """`active_frame` conta a partir do primeiro frame ativo do golpe."""
    end = hb.end if hb.end >= 0 else 10**9
    return hb.start <= active_frame <= end


def knockback(hb: HitboxDef, target_damage: float, weight: float, mult: float = 1.0) -> float:
    """Velocidade de lançamento (px/s). Cresce com o % do alvo (já somado o dano do golpe)."""
    growth = hb.growth * C.KB_GROWTH_SCALE
    return (hb.base + growth * target_damage) * mult / max(weight, 0.1)


def hitstun_frames(kb: float) -> int:
    return max(C.MIN_HITSTUN, int(kb * C.HITSTUN_PER_KB))


def hitlag_frames(dmg: float) -> int:
    return C.HITLAG_BASE + int(dmg // 4)


def launch_vector(
    angle_deg: float, kb: float, facing: int, di_x: int, di_y: int,
) -> tuple[float, float]:
    """Vetor de lançamento; o direcional do alvo (DI) gira o ângulo até DI_MAX_DEG."""
    ang = math.radians(angle_deg)
    vx, vy = math.cos(ang) * facing, math.sin(ang)
    if di_x or di_y:
        a = math.atan2(vy, vx)
        want = math.atan2(di_y, di_x)
        diff = (want - a + math.pi) % (2 * math.pi) - math.pi
        lim = math.radians(C.DI_MAX_DEG)
        a += max(-lim, min(lim, diff))
        vx, vy = math.cos(a), math.sin(a)
    return vx * kb, vy * kb
