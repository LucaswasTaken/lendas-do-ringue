"""Colisão de um corpo AABB (pés no centro-base) contra as plataformas do palco.

Usa testes de travessia (posição anterior x nova) em vez de sobreposição, então
velocidades altas de knockback não atravessam plataformas finas.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.content import Platform

EPS = 0.01


@dataclass
class MoveResult:
    landed: bool = False
    hit_ceiling: bool = False
    hit_wall: bool = False
    platform: Platform | None = None


def _overlap_x(x: float, half_w: float, p: Platform) -> bool:
    return x + half_w > p.x and x - half_w < p.right


def _overlap_y(y: float, h: float, p: Platform) -> bool:
    return y + h > p.y and y < p.top


def move_body(
    x: float, y: float, vx: float, vy: float, half_w: float, h: float, dt: float,
    platforms: tuple[Platform, ...], ignore_soft: bool,
) -> tuple[float, float, float, float, MoveResult]:
    """Move o corpo e devolve (x, y, vx, vy, resultado)."""
    res = MoveResult()

    # Eixo X: só plataformas sólidas bloqueiam.
    nx = x + vx * dt
    for p in platforms:
        if p.soft or not _overlap_y(y, h, p):
            continue
        if vx > 0 and x + half_w <= p.x + EPS and nx + half_w > p.x:
            nx = p.x - half_w
            vx = 0.0
            res.hit_wall = True
        elif vx < 0 and x - half_w >= p.right - EPS and nx - half_w < p.right:
            nx = p.right + half_w
            vx = 0.0
            res.hit_wall = True
    x = nx

    # Eixo Y.
    ny = y + vy * dt
    if vy <= 0:
        best: Platform | None = None
        for p in platforms:
            if p.soft and ignore_soft:
                continue
            if not _overlap_x(x, half_w, p):
                continue
            if y >= p.top - EPS and ny <= p.top and (best is None or p.top > best.top):
                best = p
        if best is not None:
            ny = best.top
            vy = 0.0
            res.landed = True
            res.platform = best
    else:
        for p in platforms:
            if p.soft or not _overlap_x(x, half_w, p):
                continue
            if y + h <= p.y + EPS and ny + h > p.y:
                ny = p.y - h
                vy = 0.0
                res.hit_ceiling = True
    return x, ny, vx, vy, res


def support_under(
    x: float, y: float, half_w: float, platforms: tuple[Platform, ...], ignore_soft: bool,
) -> Platform | None:
    """Plataforma em que os pés estão apoiados agora (ou None)."""
    for p in platforms:
        if p.soft and ignore_soft:
            continue
        if abs(y - p.top) < 0.5 and _overlap_x(x, half_w, p):
            return p
    return None
