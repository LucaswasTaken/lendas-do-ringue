"""Carrega lutadores e palcos dos YAML em content/ para dataclasses imutáveis."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import yaml

from shared.paths import content_dir

# Golpes que todo lutador precisa ter.
MOVE_KEYS = (
    "light_neutral", "light_side", "light_down",
    "air_neutral", "air_side", "air_down",
    "heavy_neutral", "heavy_side", "heavy_down",
    "recovery", "air_heavy_down",
)


@dataclass(frozen=True)
class HitboxDef:
    x: float  # centro, à frente do lutador (espelhado pela direção)
    y: float  # centro, acima dos pés
    w: float
    h: float
    dmg: float
    angle: float  # graus; 0 = para frente, 90 = para cima, -90 = para baixo
    base: float  # knockback fixo (px/s)
    growth: float  # knockback extra por ponto de % do alvo
    start: int = 0  # janela dentro dos frames ativos (0 = primeiro frame ativo)
    end: int = -1  # -1 = até o fim dos frames ativos


@dataclass(frozen=True)
class MoveDef:
    key: str
    name: str
    startup: int
    active: int
    recovery: int
    hitboxes: tuple[HitboxDef, ...]
    charge: int = 0  # frames máximos de carga (só golpes fortes)
    impulse: tuple[float, float] | None = None  # (vx para frente, vy) aplicado no 1º frame ativo
    landing_lag: int = 6

    @property
    def total(self) -> int:
        return self.startup + self.active + self.recovery


@dataclass(frozen=True)
class FighterDef:
    key: str
    name: str
    color: tuple[int, int, int]
    weight: float
    speed: float
    air_jumps: int
    width: float
    height: float
    moves: dict[str, MoveDef] = field(hash=False)
    weapon: str = "sword"  # sword | hammer | claws | spear (só visual)
    accent: tuple[int, int, int] = (230, 230, 240)
    hair: tuple[int, int, int] = (50, 40, 40)


@dataclass(frozen=True)
class Platform:
    x: float  # canto esquerdo
    y: float  # base
    w: float
    h: float
    soft: bool = False

    @property
    def top(self) -> float:
        return self.y + self.h

    @property
    def right(self) -> float:
        return self.x + self.w


@dataclass(frozen=True)
class StageDef:
    key: str
    name: str
    platforms: tuple[Platform, ...]
    blast: tuple[float, float, float, float]  # esquerda, direita, baixo, cima
    spawns: tuple[tuple[float, float], ...]
    background: tuple[int, int, int] = (24, 26, 40)


def _move(key: str, d: dict) -> MoveDef:
    hbs = tuple(
        HitboxDef(
            x=float(h["x"]), y=float(h["y"]), w=float(h["w"]), h=float(h["h"]),
            dmg=float(h["dmg"]), angle=float(h.get("angle", 30)),
            base=float(h.get("base", 300)), growth=float(h.get("growth", 6)),
            start=int(h.get("start", 0)), end=int(h.get("end", -1)),
        )
        for h in d.get("hitboxes", [])
    )
    imp = d.get("impulse")
    return MoveDef(
        key=key, name=d.get("name", key), startup=int(d["startup"]), active=int(d["active"]),
        recovery=int(d["recovery"]), hitboxes=hbs, charge=int(d.get("charge", 0)),
        impulse=(float(imp[0]), float(imp[1])) if imp else None,
        landing_lag=int(d.get("landing_lag", 6)),
    )


def load_fighter(path: Path) -> FighterDef:
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    moves = d.get("moves", {})
    missing = [k for k in MOVE_KEYS if k not in moves]
    if missing:
        raise ValueError(f"{path.name}: faltam golpes {missing}")
    hb = d.get("hurtbox", {})
    look = d.get("look", {})
    return FighterDef(
        weapon=str(look.get("weapon", "sword")),
        accent=tuple(look.get("accent", [230, 230, 240])),
        hair=tuple(look.get("hair", [50, 40, 40])),
        key=path.stem, name=d["name"], color=tuple(d.get("color", [200, 200, 200])),
        weight=float(d.get("weight", 1.0)), speed=float(d.get("speed", 1.0)),
        air_jumps=int(d.get("air_jumps", 2)),
        width=float(hb.get("w", 50)), height=float(hb.get("h", 110)),
        moves={k: _move(k, v) for k, v in moves.items()},
    )


def load_stage(path: Path) -> StageDef:
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    plats = tuple(
        Platform(float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"]),
                 bool(p.get("soft", False)))
        for p in d["platforms"]
    )
    b = d["blast"]
    return StageDef(
        key=path.stem, name=d["name"], platforms=plats,
        blast=(float(b["left"]), float(b["right"]), float(b["bottom"]), float(b["top"])),
        spawns=tuple((float(x), float(y)) for x, y in d["spawns"]),
        background=tuple(d.get("background", [24, 26, 40])),
    )


@cache
def fighters() -> dict[str, FighterDef]:
    return {p.stem: load_fighter(p)
            for p in sorted((content_dir() / "fighters").glob("*.yaml"))}


@cache
def stages() -> dict[str, StageDef]:
    return {p.stem: load_stage(p) for p in sorted((content_dir() / "stages").glob("*.yaml"))}
