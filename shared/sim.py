"""Simulação da partida: pura e determinística (mesmos inputs = mesmo estado).

`World.step(inputs)` avança 1 frame recebendo o bitmask de botões de cada jogador.
O servidor roda isto de forma autoritativa; o cliente roda a mesma coisa para predição.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared import combat
from shared import constants as C
from shared import inputs as I
from shared.content import FighterDef, MoveDef, StageDef
from shared.physics import move_body, support_under

AIR_MOVES = {"air_neutral", "air_side", "air_down", "recovery", "air_heavy_down"}
ACTIONABLE = {"idle", "run", "air"}


@dataclass
class Fighter:
    pid: int
    fdef: FighterDef
    team: int
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    facing: int = 1
    state: str = "air"
    grounded: bool = False
    jumps_left: int = 0
    recovery_used: bool = False
    fastfall: bool = False
    damage: float = 0.0
    stocks: int = C.STOCKS
    move: MoveDef | None = None
    move_frame: int = 0
    charge: int = 0
    charging: bool = False
    hit_ids: set[int] = field(default_factory=set)
    hitstun: int = 0
    hitlag: int = 0
    invuln: int = 0
    dodge_timer: int = 0
    dodge_cd: int = 0
    lag: int = 0
    drop: int = 0
    respawn: int = 0
    ledge_side: int = 0  # +1 pendurado à direita da quina, -1 à esquerda
    ledge_timer: int = 0
    ledge_cd: int = 0
    prev_bits: int = 0
    buffer: dict[int, int] = field(default_factory=dict)
    last_hit_by: int | None = None
    kos: int = 0
    falls: int = 0
    dealt: float = 0.0

    @property
    def half_w(self) -> float:
        return self.fdef.width / 2

    @property
    def alive(self) -> bool:
        return self.state not in ("ko", "out")

    def consume(self, button: int) -> bool:
        if self.buffer.get(button, 0) > 0:
            self.buffer[button] = 0
            return True
        return False


class World:
    def __init__(
        self, stage: StageDef, roster: list[tuple[int, FighterDef]],
        teams: dict[int, int] | None = None, stocks: int = C.STOCKS,
        seconds: int = C.MATCH_SECONDS,
    ) -> None:
        self.stage = stage
        self.frame = 0
        self.max_frames = seconds * C.TICK_RATE
        self.events: list[dict] = []
        self.over = False
        self.winner: int | None = None  # time vencedor (team)
        self.fighters: dict[int, Fighter] = {}
        # quinas agarráveis: (x da quina, topo, lado onde o lutador fica pendurado)
        self.ledges: list[tuple[float, float, int]] = []
        for pl in stage.platforms:
            if not pl.soft:
                self.ledges += [(pl.x, pl.top, -1), (pl.right, pl.top, 1)]
        teams = teams or {}
        for pid, fdef in roster:
            f = Fighter(pid=pid, fdef=fdef, team=teams.get(pid, pid), stocks=stocks)
            self._spawn(f, invuln=0)
            self.fighters[pid] = f

    # ------------------------------------------------------------------ ciclo
    def step(self, inputs: dict[int, int]) -> None:
        self.events = []
        if self.over:
            return
        self.frame += 1
        for f in self.fighters.values():
            self._update(f, inputs.get(f.pid, 0))
        self._resolve_hits()
        for f in self.fighters.values():
            self._check_blast(f)
        self._check_end()

    def _update(self, f: Fighter, bits: int) -> None:
        pressed = bits & ~f.prev_bits
        f.prev_bits = bits
        for b in I.BUFFERED:
            if pressed & b:
                f.buffer[b] = C.INPUT_BUFFER
        if f.state == "out":
            return
        if f.state == "ko":
            f.respawn -= 1
            if f.respawn <= 0:
                self._spawn(f, invuln=C.RESPAWN_INVULN)
            return
        if f.hitlag > 0:
            f.hitlag -= 1
            return
        for attr in ("invuln", "dodge_cd", "drop", "ledge_cd"):
            v = getattr(f, attr)
            if v > 0:
                setattr(f, attr, v - 1)

        ax, ay = I.axis_x(bits), I.axis_y(bits)
        if f.state == "hitstun":
            self._tick_hitstun(f)
        elif f.state == "attack":
            self._tick_attack(f, bits, ax)
        elif f.state == "dodge":
            self._tick_dodge(f)
        elif f.state == "land":
            f.lag -= 1
            self._friction(f)
            if f.lag <= 0:
                f.state = "idle"
        elif f.state == "ledge":
            self._tick_ledge(f, pressed, ax)
        else:
            self._actionable(f, bits, pressed, ax, ay)

        if f.state != "ledge":
            self._integrate(f)
            self._try_ledge(f)
        for b in I.BUFFERED:
            if f.buffer.get(b, 0) > 0:
                f.buffer[b] -= 1

    # ------------------------------------------------------------------ estados
    def _actionable(self, f: Fighter, bits: int, pressed: int, ax: int, ay: int) -> None:
        if f.dodge_cd == 0 and f.consume(I.DODGE):
            self._start_dodge(f, ax, ay)
            return
        if f.consume(I.JUMP):
            if f.grounded:
                f.vy = C.JUMP_VEL
                f.grounded = False
                f.fastfall = False
                self.events.append({"e": "jump", "p": f.pid, "x": f.x, "y": f.y})
            elif f.jumps_left > 0:
                f.jumps_left -= 1
                f.vy = C.AIR_JUMP_VEL
                f.fastfall = False
                self.events.append({"e": "jump", "p": f.pid, "x": f.x, "y": f.y, "air": 1})
        if f.consume(I.LIGHT) and self._start_attack(f, light=True, ax=ax, ay=ay):
            return
        if f.consume(I.HEAVY) and self._start_attack(f, light=False, ax=ax, ay=ay):
            return

        speed = f.fdef.speed
        if f.grounded:
            if ax:
                f.facing = ax
                f.vx = _approach(f.vx, ax * C.RUN_SPEED * speed, C.GROUND_ACCEL * C.TICK_DT)
                f.state = "run"
            else:
                self._friction(f)
                f.state = "idle"
            plat = support_under(f.x, f.y, f.half_w, self.stage.platforms, False)
            if pressed & I.DOWN and plat is not None and plat.soft:
                f.drop = C.DROP_THROUGH_FRAMES
                f.grounded = False
                f.state = "air"
        else:
            f.state = "air"
            if ax:
                f.vx = _approach(f.vx, ax * C.AIR_SPEED * speed, C.AIR_ACCEL * C.TICK_DT)
            else:
                f.vx = _approach(f.vx, 0.0, C.AIR_FRICTION * C.TICK_DT)
            if pressed & I.DOWN and f.vy <= 0:
                f.fastfall = True

    def _start_attack(self, f: Fighter, light: bool, ax: int, ay: int) -> bool:
        if f.grounded:
            kind = "light" if light else "heavy"
            key = f"{kind}_down" if ay < 0 else f"{kind}_side" if ax else f"{kind}_neutral"
        elif light:
            key = "air_down" if ay < 0 else "air_side" if ax else "air_neutral"
        elif ay < 0:
            key = "air_heavy_down"
        else:
            if f.recovery_used:
                return False
            key = "recovery"
            f.recovery_used = True
        if ax and key.endswith("_side"):
            f.facing = ax
        f.state = "attack"
        f.move = f.fdef.moves[key]
        f.move_frame = 0
        f.charge = 0
        f.charging = f.move.charge > 0
        f.hit_ids = set()
        self.events.append({"e": "attack", "p": f.pid, "m": key})
        return True

    def _tick_attack(self, f: Fighter, bits: int, ax: int) -> None:
        m = f.move
        assert m is not None
        at_charge_frame = f.charging and f.move_frame == m.startup - 1
        if at_charge_frame and bits & I.HEAVY and f.charge < m.charge:
            f.charge += 1
        else:
            if at_charge_frame:
                f.charging = False  # soltou o botão ou chegou na carga máxima
            f.move_frame += 1
        if f.move_frame == m.startup and not f.charging and m.impulse:
            ix, iy = m.impulse
            f.vx = ix * f.facing
            if iy:
                f.vy = iy
                f.grounded = False
                f.fastfall = False
        if f.grounded:
            self._friction(f)
        elif ax:
            f.vx = _approach(f.vx, ax * C.AIR_SPEED * f.fdef.speed, C.AIR_ACCEL * 0.5 * C.TICK_DT)
        if f.move_frame >= m.total:
            self._end_move(f)

    def _end_move(self, f: Fighter) -> None:
        f.move = None
        f.charging = False
        f.state = "idle" if f.grounded else "air"

    def _start_dodge(self, f: Fighter, ax: int, ay: int) -> None:
        f.state = "dodge"
        f.dodge_timer = C.DODGE_FRAMES
        f.invuln = max(f.invuln, C.DODGE_INVULN)
        f.dodge_cd = C.DODGE_COOLDOWN
        if f.grounded:
            f.vx = ax * C.DODGE_SPEED
        else:
            n = (ax * ax + ay * ay) ** 0.5 or 1.0
            f.vx = ax / n * C.DODGE_SPEED * 0.85
            f.vy = ay / n * C.DODGE_SPEED * 0.85
            f.fastfall = False
        self.events.append({"e": "dodge", "p": f.pid, "x": f.x, "y": f.y})

    def _tick_dodge(self, f: Fighter) -> None:
        f.dodge_timer -= 1
        f.vx *= 0.94
        if not f.grounded:
            f.vy *= 0.94
        if f.dodge_timer <= 0:
            if not f.grounded:
                f.vx *= 0.5
                f.vy *= 0.5
            f.state = "idle" if f.grounded else "air"

    # ------------------------------------------------------------------ borda
    def _try_ledge(self, f: Fighter) -> None:
        can = f.state == "air" or (
            f.state == "attack" and f.move is not None and f.move.key == "recovery"
            and f.move_frame >= f.move.startup)
        if not can or f.grounded or f.vy > 0 or f.ledge_cd > 0:
            return
        h = f.fdef.height
        hand_y = f.y + h * C.LEDGE_HANG
        for ex, top, side in self.ledges:
            if abs(hand_y - top) > C.LEDGE_REACH:
                continue
            if (f.x - ex) * side <= 0 or abs(f.x - side * f.half_w - ex) > C.LEDGE_REACH:
                continue
            if any(o is not f and o.state == "ledge" and o.ledge_side == side
                   and abs(o.x - side * o.half_w - ex) < 1 for o in self.fighters.values()):
                continue  # quina ocupada
            f.state = "ledge"
            f.move = None
            f.ledge_side = side
            f.ledge_timer = 0
            f.x = ex + side * f.half_w
            f.y = top - h * C.LEDGE_HANG
            f.vx = f.vy = 0.0
            f.facing = -side
            f.jumps_left = f.fdef.air_jumps
            f.recovery_used = False
            f.fastfall = False
            f.invuln = max(f.invuln, C.LEDGE_INVULN)
            self.events.append({"e": "ledge", "p": f.pid, "x": ex, "y": top})
            return

    def _tick_ledge(self, f: Fighter, pressed: int, ax: int) -> None:
        f.ledge_timer += 1
        side = f.ledge_side
        inward = -side  # direção do palco
        ex = f.x - side * f.half_w
        top = f.y + f.fdef.height * C.LEDGE_HANG
        toward = I.RIGHT if inward > 0 else I.LEFT
        away = I.LEFT if inward > 0 else I.RIGHT
        if f.consume(I.JUMP):
            f.state = "air"
            f.vy = C.JUMP_VEL
            f.ledge_cd = C.LEDGE_REGRAB
            self.events.append({"e": "jump", "p": f.pid, "x": f.x, "y": f.y})
        elif pressed & (I.UP | toward) or f.consume(I.LIGHT) or f.consume(I.HEAVY):
            f.x = ex + inward * (f.half_w + 4)
            f.y = top
            f.vx = f.vy = 0.0
            f.grounded = True
            f.state = "idle"
            f.ledge_cd = C.LEDGE_REGRAB
            f.invuln = max(f.invuln, 8)
        elif pressed & (I.DOWN | away) or f.ledge_timer > C.LEDGE_MAX:
            f.state = "air"
            f.vx = -inward * 60.0
            f.ledge_cd = C.LEDGE_REGRAB

    def _tick_hitstun(self, f: Fighter) -> None:
        f.hitstun -= 1
        f.vx *= C.KB_DECAY
        if f.vy > 0:
            f.vy *= C.KB_DECAY
        if f.grounded:
            self._friction(f)
        if f.hitstun <= 0:
            f.state = "idle" if f.grounded else "air"

    def _friction(self, f: Fighter) -> None:
        if f.grounded:
            f.vx = _approach(f.vx, 0.0, C.GROUND_FRICTION * C.TICK_DT)

    # ------------------------------------------------------------------ física
    def _integrate(self, f: Fighter) -> None:
        airdodge = f.state == "dodge" and not f.grounded
        if not f.grounded and not airdodge:
            g = C.GRAVITY * (C.HITSTUN_GRAVITY if f.state == "hitstun" else 1.0)
            f.vy -= g * C.TICK_DT
            limit = C.FAST_FALL if f.fastfall else C.MAX_FALL
            if f.vy < -limit and f.state != "hitstun":
                f.vy = -limit
        pre_vy = f.vy
        f.x, f.y, f.vx, f.vy, res = move_body(
            f.x, f.y, f.vx, f.vy, f.half_w, f.fdef.height, C.TICK_DT,
            self.stage.platforms, ignore_soft=f.drop > 0,
        )
        if res.landed and not f.grounded:
            if f.state == "hitstun" and pre_vy < -700:
                f.vy = -pre_vy * 0.45  # quica no chão
                return
            self._land(f)
        elif f.grounded and support_under(
            f.x, f.y, f.half_w, self.stage.platforms, f.drop > 0
        ) is None:
            f.grounded = False
            if f.state in ("idle", "run"):
                f.state = "air"

    def _land(self, f: Fighter) -> None:
        f.grounded = True
        f.jumps_left = f.fdef.air_jumps
        f.recovery_used = False
        f.fastfall = False
        f.last_hit_by = None
        if f.state == "attack" and f.move and f.move.key in AIR_MOVES:
            f.lag = f.move.landing_lag
            f.move = None
            f.state = "land"
        elif f.state == "air":
            f.state = "idle"
        elif f.state == "dodge":
            f.state = "idle"

    # ------------------------------------------------------------------ combate
    def _resolve_hits(self) -> None:
        hits = []
        for att in self.fighters.values():
            m = att.move
            if att.state != "attack" or m is None or att.hitlag > 0:
                continue
            af = att.move_frame - m.startup
            if not (0 <= af < m.active) or att.charging:
                continue
            for tgt in self.fighters.values():
                if (tgt is att or tgt.pid in att.hit_ids or not tgt.alive
                        or tgt.invuln > 0 or tgt.team == att.team):
                    continue
                hurt = combat.hurtbox_rect(tgt.x, tgt.y, tgt.fdef.width, tgt.fdef.height)
                for hb in m.hitboxes:
                    if not combat.hitbox_active(hb, af):
                        continue
                    if combat.overlaps(combat.hitbox_rect(hb, att.x, att.y, att.facing), hurt):
                        hits.append((att, tgt, hb))
                        break
        for att, tgt, hb in hits:  # aplica depois: trocas simultâneas são justas
            self._apply_hit(att, tgt, hb)

    def _apply_hit(self, att: Fighter, tgt: Fighter, hb) -> None:
        m = att.move
        mult = 1.0 + C.CHARGE_BONUS * att.charge / m.charge if m and m.charge else 1.0
        dmg = hb.dmg * mult
        att.hit_ids.add(tgt.pid)
        tgt.damage = min(C.MAX_DAMAGE, tgt.damage + dmg)
        att.dealt += dmg
        kb = combat.knockback(hb, tgt.damage, tgt.fdef.weight, mult)
        vx, vy = combat.launch_vector(
            hb.angle, kb, att.facing, I.axis_x(tgt.prev_bits), I.axis_y(tgt.prev_bits))
        if tgt.grounded and vy < 0:
            vy = -vy * 0.5
        tgt.vx, tgt.vy = vx, vy
        if vy > 0:
            tgt.grounded = False
        tgt.state = "hitstun"
        tgt.hitstun = combat.hitstun_frames(kb)
        tgt.move = None
        tgt.charging = False
        tgt.fastfall = False
        tgt.recovery_used = False
        tgt.jumps_left = max(tgt.jumps_left, 1)
        tgt.last_hit_by = att.pid
        lag = combat.hitlag_frames(dmg)
        att.hitlag = max(att.hitlag, lag)
        tgt.hitlag = lag
        self.events.append({"e": "hit", "a": att.pid, "t": tgt.pid, "x": tgt.x,
                            "y": tgt.y + tgt.fdef.height / 2, "dmg": round(dmg, 1),
                            "kb": round(kb)})

    # ------------------------------------------------------------------ partida
    def _spawn(self, f: Fighter, invuln: int) -> None:
        sx, sy = self.stage.spawns[f.pid % len(self.stage.spawns)]
        f.x, f.y, f.vx, f.vy = sx, sy, 0.0, 0.0
        f.state = "air"
        f.grounded = False
        f.damage = 0.0
        f.jumps_left = f.fdef.air_jumps
        f.recovery_used = False
        f.invuln = invuln
        f.move = None
        f.hitstun = f.hitlag = 0
        f.last_hit_by = None
        f.facing = 1 if sx < 0 else -1

    def _check_blast(self, f: Fighter) -> None:
        if not f.alive:
            return
        left, right, bottom, top = self.stage.blast
        if left < f.x < right and bottom < f.y < top:
            return
        f.stocks -= 1
        f.falls += 1
        killer = self.fighters.get(f.last_hit_by) if f.last_hit_by is not None else None
        if killer is not None:
            killer.kos += 1
        self.events.append({"e": "ko", "p": f.pid, "x": f.x, "y": f.y,
                            "by": f.last_hit_by})
        f.move = None
        f.vx = f.vy = 0.0
        if f.stocks > 0:
            f.state = "ko"
            f.respawn = C.RESPAWN_FRAMES
        else:
            f.state = "out"

    def _check_end(self) -> None:
        teams_alive = {f.team for f in self.fighters.values() if f.stocks > 0}
        all_teams = {f.team for f in self.fighters.values()}
        if len(all_teams) > 1 and len(teams_alive) <= 1:
            self.over = True
            self.winner = next(iter(teams_alive), None)
        elif self.frame >= self.max_frames:
            self.over = True
            best = max(self.fighters.values(), key=lambda f: (f.stocks, -f.damage))
            tied = [f for f in self.fighters.values()
                    if (f.stocks, f.damage) == (best.stocks, best.damage) and f.team != best.team]
            self.winner = None if tied else best.team
        if self.over:
            self.events.append({"e": "end", "winner": self.winner})

    @property
    def time_left(self) -> float:
        return max(0, self.max_frames - self.frame) / C.TICK_RATE

    def step_one(self, pid: int, bits: int) -> None:
        """Predição no cliente: avança só um lutador (sem golpes, KO nem relógio).

        Quem decide acertos e KOs é sempre o servidor."""
        f = self.fighters[pid]
        if not self.over:
            self._update(f, bits)

    def snapshot(self) -> dict:
        return {
            "f": self.frame,
            "over": self.over,
            "winner": self.winner,
            "fighters": [fighter_state(f) for f in self.fighters.values()],
            "events": self.events,
        }

    def apply_snapshot(self, snap: dict, only: set[int] | None = None) -> None:
        """Copia o estado de um snapshot (todos os lutadores ou só os de `only`)."""
        self.frame = snap["f"]
        self.over = snap["over"]
        self.winner = snap["winner"]
        for st in snap["fighters"]:
            if only is None or st["pid"] in only:
                apply_state(self.fighters[st["pid"]], st)


# Campos simples do Fighter que viajam no snapshot (estado completo, para a predição).
_STATE_FIELDS = (
    "x", "y", "vx", "vy", "facing", "state", "grounded", "jumps_left", "recovery_used",
    "fastfall", "damage", "stocks", "move_frame", "charge", "charging", "hitstun", "hitlag",
    "invuln", "dodge_timer", "dodge_cd", "lag", "drop", "respawn", "ledge_side", "ledge_timer",
    "ledge_cd", "prev_bits", "last_hit_by",
    "kos", "falls", "dealt",
)


def fighter_state(f: Fighter) -> dict:
    d = {k: getattr(f, k) for k in _STATE_FIELDS}
    d["pid"] = f.pid
    d["move"] = f.move.key if f.move else None
    d["hit_ids"] = sorted(f.hit_ids)
    d["buffer"] = [f.buffer.get(b, 0) for b in I.BUFFERED]
    return d


def apply_state(f: Fighter, d: dict) -> None:
    for k in _STATE_FIELDS:
        setattr(f, k, d[k])
    f.move = f.fdef.moves[d["move"]] if d["move"] else None
    f.hit_ids = set(d["hit_ids"])
    f.buffer = dict(zip(I.BUFFERED, d["buffer"], strict=True))


def _approach(v: float, target: float, delta: float) -> float:
    if v < target:
        return min(v + delta, target)
    return max(v - delta, target)
