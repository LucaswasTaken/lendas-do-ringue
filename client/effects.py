"""Partículas e tremor de tela, alimentados pelos eventos da simulação."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import arcade


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: tuple[int, int, int]


class Effects:
    def __init__(self) -> None:
        self.particles: list[Particle] = []
        self.shake = 0.0
        self.rng = random.Random()

    def burst(self, x: float, y: float, color, n: int, speed: float, life: float,
              size: float) -> None:
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            s = self.rng.uniform(speed * 0.3, speed)
            lf = self.rng.uniform(life * 0.5, life)
            self.particles.append(Particle(x, y, math.cos(a) * s, math.sin(a) * s, lf, lf,
                                           self.rng.uniform(size * 0.5, size), color))

    def on_event(self, ev: dict, colors: dict[int, tuple[int, int, int]]) -> None:
        e = ev["e"]
        if e == "hit":
            strong = ev["kb"] > 1200
            self.burst(ev["x"], ev["y"], (255, 240, 160), 22 if strong else 10,
                       900 if strong else 500, 0.35, 9 if strong else 6)
            self.shake = max(self.shake, min(26.0, ev["kb"] / 90))
        elif e == "ko":
            self.burst(ev["x"], ev["y"], colors.get(ev["p"], (255, 255, 255)), 60, 1600, 0.9, 14)
            self.shake = 30.0
        elif e == "jump" and ev.get("air"):
            self.burst(ev["x"], ev["y"], (200, 200, 220), 6, 200, 0.25, 5)
        elif e == "dodge":
            self.burst(ev["x"], ev["y"] + 50, (170, 210, 255), 8, 250, 0.3, 6)

    def update(self, dt: float) -> None:
        for p in self.particles:
            p.life -= dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vx *= 0.9
            p.vy = p.vy * 0.9 - 600 * dt
        self.particles = [p for p in self.particles if p.life > 0]
        self.shake = max(0.0, self.shake - 60 * dt)

    def shake_offset(self) -> tuple[float, float]:
        if self.shake <= 0:
            return 0.0, 0.0
        return (self.rng.uniform(-self.shake, self.shake),
                self.rng.uniform(-self.shake, self.shake))

    def draw(self) -> None:
        for p in self.particles:
            a = int(255 * p.life / p.max_life)
            s = p.size * (0.4 + 0.6 * p.life / p.max_life)
            arcade.draw_lrbt_rectangle_filled(p.x - s / 2, p.x + s / 2, p.y - s / 2, p.y + s / 2,
                                              (*p.color, a))
