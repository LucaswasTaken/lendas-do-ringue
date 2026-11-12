// Port 1:1 de shared/physics.py, shared/combat.py e shared/sim.py (predição no navegador).
// Mantenha em sincronia com o Python: tests/test_web_parity.py roda os dois e compara.
// As constantes vêm do servidor (/api/content.json -> constants), via configure().

export let C = null;
export const I = {
  LEFT: 1 << 0, RIGHT: 1 << 1, UP: 1 << 2, DOWN: 1 << 3,
  JUMP: 1 << 4, LIGHT: 1 << 5, HEAVY: 1 << 6, DODGE: 1 << 7, THROW: 1 << 8,
};
const BUFFERED = [I.JUMP, I.LIGHT, I.HEAVY, I.DODGE];
const AIR_MOVES = new Set(["air_neutral", "air_side", "air_down", "recovery", "air_heavy_down"]);
const EPS = 0.01;

export function configure(constants) {
  C = constants;
}

export const axisX = (b) => (b & I.RIGHT ? 1 : 0) - (b & I.LEFT ? 1 : 0);
export const axisY = (b) => (b & I.UP ? 1 : 0) - (b & I.DOWN ? 1 : 0);

function approach(v, target, delta) {
  if (v < target) return Math.min(v + delta, target);
  return Math.max(v - delta, target);
}

// ------------------------------------------------------------------ física
const top = (p) => p.y + p.h;
const right = (p) => p.x + p.w;
const overlapX = (x, hw, p) => x + hw > p.x && x - hw < right(p);
const overlapY = (y, h, p) => y + h > p.y && y < top(p);

export function moveBody(x, y, vx, vy, hw, h, dt, platforms, ignoreSoft) {
  const res = { landed: false, hitCeiling: false, hitWall: false, platform: null };
  let nx = x + vx * dt;
  for (const p of platforms) {
    if (p.soft || !overlapY(y, h, p)) continue;
    if (vx > 0 && x + hw <= p.x + EPS && nx + hw > p.x) {
      nx = p.x - hw; vx = 0.0; res.hitWall = true;
    } else if (vx < 0 && x - hw >= right(p) - EPS && nx - hw < right(p)) {
      nx = right(p) + hw; vx = 0.0; res.hitWall = true;
    }
  }
  x = nx;
  let ny = y + vy * dt;
  if (vy <= 0) {
    let best = null;
    for (const p of platforms) {
      if (p.soft && ignoreSoft) continue;
      if (!overlapX(x, hw, p)) continue;
      if (y >= top(p) - EPS && ny <= top(p) && (best === null || top(p) > top(best))) best = p;
    }
    if (best !== null) {
      ny = top(best); vy = 0.0; res.landed = true; res.platform = best;
    }
  } else {
    for (const p of platforms) {
      if (p.soft || !overlapX(x, hw, p)) continue;
      if (y + h <= p.y + EPS && ny + h > p.y) {
        ny = p.y - h; vy = 0.0; res.hitCeiling = true;
      }
    }
  }
  return [x, ny, vx, vy, res];
}

export function supportUnder(x, y, hw, platforms, ignoreSoft) {
  for (const p of platforms) {
    if (p.soft && ignoreSoft) continue;
    if (Math.abs(y - top(p)) < 0.5 && overlapX(x, hw, p)) return p;
  }
  return null;
}

// ------------------------------------------------------------------ combate
export function hitboxRect(hb, x, y, facing) {
  const cx = x + hb.x * facing;
  const cy = y + hb.y;
  return [cx - hb.w / 2, cx + hb.w / 2, cy - hb.h / 2, cy + hb.h / 2];
}
const hurtboxRect = (x, y, w, h) => [x - w / 2, x + w / 2, y, y + h];
const overlaps = (a, b) => a[0] < b[1] && a[1] > b[0] && a[2] < b[3] && a[3] > b[2];
export function hitboxActive(hb, af) {
  const end = hb.end >= 0 ? hb.end : 1e9;
  return hb.start <= af && af <= end;
}
function knockback(hb, dmg, weight, mult) {
  const growth = hb.growth * C.KB_GROWTH_SCALE;
  return (hb.base + growth * dmg) * mult / Math.max(weight, 0.1);
}
const hitstunFrames = (kb) => Math.max(C.MIN_HITSTUN, Math.trunc(kb * C.HITSTUN_PER_KB));
const hitlagFrames = (dmg) => C.HITLAG_BASE + Math.floor(dmg / 4);
function launchVector(angleDeg, kb, facing, dix, diy) {
  const ang = angleDeg * Math.PI / 180;
  let vx = Math.cos(ang) * facing;
  let vy = Math.sin(ang);
  if (dix || diy) {
    let a = Math.atan2(vy, vx);
    const want = Math.atan2(diy, dix);
    const tau = 2 * Math.PI;
    let diff = (want - a + Math.PI) % tau;
    if (diff < 0) diff += tau; // % do Python é sempre positivo
    diff -= Math.PI;
    const lim = C.DI_MAX_DEG * Math.PI / 180;
    a += Math.max(-lim, Math.min(lim, diff));
    vx = Math.cos(a); vy = Math.sin(a);
  }
  return [vx * kb, vy * kb];
}

// ------------------------------------------------------------------ lutador
export const STATE_FIELDS = [
  "x", "y", "vx", "vy", "facing", "state", "grounded", "jumps_left", "recovery_used",
  "fastfall", "damage", "stocks", "move_frame", "charge", "charging", "hitstun", "hitlag",
  "invuln", "dodge_timer", "dodge_cd", "lag", "drop", "respawn", "ledge_side", "ledge_timer",
  "ledge_cd", "prev_bits", "last_hit_by", "kos", "falls", "dealt",
];

export class Fighter {
  constructor(pid, fdef, team, stocks) {
    Object.assign(this, {
      pid, fdef, team, x: 0, y: 0, vx: 0, vy: 0, facing: 1, state: "air", grounded: false,
      jumps_left: 0, recovery_used: false, fastfall: false, damage: 0, stocks,
      move: null, move_frame: 0, charge: 0, charging: false, hit_ids: new Set(), hitstun: 0,
      hitlag: 0, invuln: 0, dodge_timer: 0, dodge_cd: 0, lag: 0, drop: 0, respawn: 0,
      ledge_side: 0, ledge_timer: 0, ledge_cd: 0, prev_bits: 0, buffer: new Map(),
      last_hit_by: null, kos: 0, falls: 0, dealt: 0,
    });
  }
  get halfW() { return this.fdef.width / 2; }
  get alive() { return this.state !== "ko" && this.state !== "out"; }
  consume(button) {
    if ((this.buffer.get(button) || 0) > 0) { this.buffer.set(button, 0); return true; }
    return false;
  }
}

export function applyState(f, d) {
  for (const k of STATE_FIELDS) f[k] = d[k];
  f.move = d.move ? f.fdef.moves[d.move] : null;
  f.hit_ids = new Set(d.hit_ids);
  f.buffer = new Map(BUFFERED.map((b, i) => [b, d.buffer[i]]));
}

export function fighterState(f) {
  const d = {};
  for (const k of STATE_FIELDS) d[k] = f[k];
  d.pid = f.pid;
  d.move = f.move ? f.move.key : null;
  d.hit_ids = [...f.hit_ids].sort((a, b) => a - b);
  d.buffer = BUFFERED.map((b) => f.buffer.get(b) || 0);
  return d;
}

// ------------------------------------------------------------------ mundo
export class World {
  constructor(stage, roster, { stocks = C.STOCKS, seconds = C.MATCH_SECONDS } = {}) {
    this.stage = stage;
    this.frame = 0;
    this.maxFrames = seconds * C.TICK_RATE;
    this.events = [];
    this.over = false;
    this.winner = null;
    this.fighters = new Map();
    this.ledges = [];
    for (const p of stage.platforms) {
      if (!p.soft) this.ledges.push([p.x, top(p), -1], [right(p), top(p), 1]);
    }
    for (const [pid, fdef] of roster) {
      const f = new Fighter(pid, fdef, pid, stocks);
      this.spawn(f, 0);
      this.fighters.set(pid, f);
    }
  }

  get timeLeft() { return Math.max(0, this.maxFrames - this.frame) / C.TICK_RATE; }

  step(inputs) {
    this.events = [];
    if (this.over) return;
    this.frame += 1;
    for (const f of this.fighters.values()) this.update(f, inputs[f.pid] || 0);
    this.resolveHits();
    for (const f of this.fighters.values()) this.checkBlast(f);
    this.checkEnd();
  }

  stepOne(pid, bits) {
    if (!this.over) this.update(this.fighters.get(pid), bits);
  }

  update(f, bits) {
    const pressed = bits & ~f.prev_bits;
    f.prev_bits = bits;
    for (const b of BUFFERED) if (pressed & b) f.buffer.set(b, C.INPUT_BUFFER);
    if (f.state === "out") return;
    if (f.state === "ko") {
      f.respawn -= 1;
      if (f.respawn <= 0) this.spawn(f, C.RESPAWN_INVULN);
      return;
    }
    if (f.hitlag > 0) { f.hitlag -= 1; return; }
    for (const k of ["invuln", "dodge_cd", "drop", "ledge_cd"]) if (f[k] > 0) f[k] -= 1;
    const ax = axisX(bits), ay = axisY(bits);
    if (f.state === "hitstun") this.tickHitstun(f);
    else if (f.state === "attack") this.tickAttack(f, bits, ax);
    else if (f.state === "dodge") this.tickDodge(f);
    else if (f.state === "land") {
      f.lag -= 1;
      this.friction(f);
      if (f.lag <= 0) f.state = "idle";
    } else if (f.state === "ledge") this.tickLedge(f, pressed, ax);
    else this.actionable(f, bits, pressed, ax, ay);
    if (f.state !== "ledge") {
      this.integrate(f);
      this.tryLedge(f);
    }
    for (const b of BUFFERED) if ((f.buffer.get(b) || 0) > 0) f.buffer.set(b, f.buffer.get(b) - 1);
  }

  actionable(f, bits, pressed, ax, ay) {
    if (f.dodge_cd === 0 && f.consume(I.DODGE)) { this.startDodge(f, ax, ay); return; }
    if (f.consume(I.JUMP)) {
      if (f.grounded) {
        f.vy = C.JUMP_VEL; f.grounded = false; f.fastfall = false;
        this.events.push({ e: "jump", p: f.pid, x: f.x, y: f.y });
      } else if (f.jumps_left > 0) {
        f.jumps_left -= 1; f.vy = C.AIR_JUMP_VEL; f.fastfall = false;
        this.events.push({ e: "jump", p: f.pid, x: f.x, y: f.y, air: 1 });
      }
    }
    if (f.consume(I.LIGHT) && this.startAttack(f, true, ax, ay)) return;
    if (f.consume(I.HEAVY) && this.startAttack(f, false, ax, ay)) return;
    const speed = f.fdef.speed;
    if (f.grounded) {
      if (ax) {
        f.facing = ax;
        f.vx = approach(f.vx, ax * C.RUN_SPEED * speed, C.GROUND_ACCEL * C.TICK_DT);
        f.state = "run";
      } else {
        this.friction(f);
        f.state = "idle";
      }
      const plat = supportUnder(f.x, f.y, f.halfW, this.stage.platforms, false);
      if (pressed & I.DOWN && plat !== null && plat.soft) {
        f.drop = C.DROP_THROUGH_FRAMES; f.grounded = false; f.state = "air";
      }
    } else {
      f.state = "air";
      if (ax) f.vx = approach(f.vx, ax * C.AIR_SPEED * speed, C.AIR_ACCEL * C.TICK_DT);
      else f.vx = approach(f.vx, 0.0, C.AIR_FRICTION * C.TICK_DT);
      if (pressed & I.DOWN && f.vy <= 0) f.fastfall = true;
    }
  }

  startAttack(f, light, ax, ay) {
    let key;
    if (f.grounded) {
      const kind = light ? "light" : "heavy";
      key = ay < 0 ? `${kind}_down` : ax ? `${kind}_side` : `${kind}_neutral`;
    } else if (light) {
      key = ay < 0 ? "air_down" : ax ? "air_side" : "air_neutral";
    } else if (ay < 0) {
      key = "air_heavy_down";
    } else {
      if (f.recovery_used) return false;
      key = "recovery";
      f.recovery_used = true;
    }
    if (ax && key.endsWith("_side")) f.facing = ax;
    f.state = "attack";
    f.move = f.fdef.moves[key];
    f.move_frame = 0;
    f.charge = 0;
    f.charging = f.move.charge > 0;
    f.hit_ids = new Set();
    this.events.push({ e: "attack", p: f.pid, m: key });
    return true;
  }

  tickAttack(f, bits, ax) {
    const m = f.move;
    const atCharge = f.charging && f.move_frame === m.startup - 1;
    if (atCharge && bits & I.HEAVY && f.charge < m.charge) {
      f.charge += 1;
    } else {
      if (atCharge) f.charging = false;
      f.move_frame += 1;
    }
    if (f.move_frame === m.startup && !f.charging && m.impulse) {
      const [ix, iy] = m.impulse;
      f.vx = ix * f.facing;
      if (iy) { f.vy = iy; f.grounded = false; f.fastfall = false; }
    }
    if (f.grounded) this.friction(f);
    else if (ax) {
      f.vx = approach(f.vx, ax * C.AIR_SPEED * f.fdef.speed, C.AIR_ACCEL * 0.5 * C.TICK_DT);
    }
    if (f.move_frame >= m.total) this.endMove(f);
  }

  endMove(f) {
    f.move = null; f.charging = false; f.state = f.grounded ? "idle" : "air";
  }

  startDodge(f, ax, ay) {
    f.state = "dodge";
    f.dodge_timer = C.DODGE_FRAMES;
    f.invuln = Math.max(f.invuln, C.DODGE_INVULN);
    f.dodge_cd = C.DODGE_COOLDOWN;
    if (f.grounded) {
      f.vx = ax * C.DODGE_SPEED;
    } else {
      const n = Math.sqrt(ax * ax + ay * ay) || 1.0;
      f.vx = ax / n * C.DODGE_SPEED * 0.85;
      f.vy = ay / n * C.DODGE_SPEED * 0.85;
      f.fastfall = false;
    }
    this.events.push({ e: "dodge", p: f.pid, x: f.x, y: f.y });
  }

  tickDodge(f) {
    f.dodge_timer -= 1;
    f.vx *= 0.94;
    if (!f.grounded) f.vy *= 0.94;
    if (f.dodge_timer <= 0) {
      if (!f.grounded) { f.vx *= 0.5; f.vy *= 0.5; }
      f.state = f.grounded ? "idle" : "air";
    }
  }

  tryLedge(f) {
    const can = f.state === "air" || (f.state === "attack" && f.move !== null
      && f.move.key === "recovery" && f.move_frame >= f.move.startup);
    if (!can || f.grounded || f.vy > 0 || f.ledge_cd > 0) return;
    const h = f.fdef.height;
    const handY = f.y + h * C.LEDGE_HANG;
    for (const [ex, tp, side] of this.ledges) {
      if (Math.abs(handY - tp) > C.LEDGE_REACH) continue;
      if ((f.x - ex) * side <= 0 || Math.abs(f.x - side * f.halfW - ex) > C.LEDGE_REACH) continue;
      let taken = false;
      for (const o of this.fighters.values()) {
        if (o !== f && o.state === "ledge" && o.ledge_side === side
          && Math.abs(o.x - side * o.halfW - ex) < 1) taken = true;
      }
      if (taken) continue;
      f.state = "ledge"; f.move = null; f.ledge_side = side; f.ledge_timer = 0;
      f.x = ex + side * f.halfW; f.y = tp - h * C.LEDGE_HANG; f.vx = 0.0; f.vy = 0.0;
      f.facing = -side; f.jumps_left = f.fdef.air_jumps; f.recovery_used = false;
      f.fastfall = false; f.invuln = Math.max(f.invuln, C.LEDGE_INVULN);
      this.events.push({ e: "ledge", p: f.pid, x: ex, y: tp });
      return;
    }
  }

  tickLedge(f, pressed, ax) {
    f.ledge_timer += 1;
    const side = f.ledge_side;
    const inward = -side;
    const ex = f.x - side * f.halfW;
    const tp = f.y + f.fdef.height * C.LEDGE_HANG;
    const toward = inward > 0 ? I.RIGHT : I.LEFT;
    const away = inward > 0 ? I.LEFT : I.RIGHT;
    if (f.consume(I.JUMP)) {
      f.state = "air"; f.vy = C.JUMP_VEL; f.ledge_cd = C.LEDGE_REGRAB;
      this.events.push({ e: "jump", p: f.pid, x: f.x, y: f.y });
    } else if (pressed & (I.UP | toward) || f.consume(I.LIGHT) || f.consume(I.HEAVY)) {
      f.x = ex + inward * (f.halfW + 4); f.y = tp; f.vx = 0.0; f.vy = 0.0;
      f.grounded = true; f.state = "idle"; f.ledge_cd = C.LEDGE_REGRAB;
      f.invuln = Math.max(f.invuln, 8);
    } else if (pressed & (I.DOWN | away) || f.ledge_timer > C.LEDGE_MAX) {
      f.state = "air"; f.vx = -inward * 60.0; f.ledge_cd = C.LEDGE_REGRAB;
    }
  }

  tickHitstun(f) {
    f.hitstun -= 1;
    f.vx *= C.KB_DECAY;
    if (f.vy > 0) f.vy *= C.KB_DECAY;
    if (f.grounded) this.friction(f);
    if (f.hitstun <= 0) f.state = f.grounded ? "idle" : "air";
  }

  friction(f) {
    if (f.grounded) f.vx = approach(f.vx, 0.0, C.GROUND_FRICTION * C.TICK_DT);
  }

  integrate(f) {
    const airdodge = f.state === "dodge" && !f.grounded;
    if (!f.grounded && !airdodge) {
      const g = C.GRAVITY * (f.state === "hitstun" ? C.HITSTUN_GRAVITY : 1.0);
      f.vy -= g * C.TICK_DT;
      const limit = f.fastfall ? C.FAST_FALL : C.MAX_FALL;
      if (f.vy < -limit && f.state !== "hitstun") f.vy = -limit;
    }
    const preVy = f.vy;
    let res;
    [f.x, f.y, f.vx, f.vy, res] = moveBody(f.x, f.y, f.vx, f.vy, f.halfW, f.fdef.height,
      C.TICK_DT, this.stage.platforms, f.drop > 0);
    if (res.landed && !f.grounded) {
      if (f.state === "hitstun" && preVy < -700) { f.vy = -preVy * 0.45; return; }
      this.land(f);
    } else if (f.grounded
      && supportUnder(f.x, f.y, f.halfW, this.stage.platforms, f.drop > 0) === null) {
      f.grounded = false;
      if (f.state === "idle" || f.state === "run") f.state = "air";
    }
  }

  land(f) {
    f.grounded = true; f.jumps_left = f.fdef.air_jumps; f.recovery_used = false;
    f.fastfall = false; f.last_hit_by = null;
    if (f.state === "attack" && f.move && AIR_MOVES.has(f.move.key)) {
      f.lag = f.move.landing_lag; f.move = null; f.state = "land";
    } else if (f.state === "air" || f.state === "dodge") {
      f.state = "idle";
    }
  }

  resolveHits() {
    const hits = [];
    for (const att of this.fighters.values()) {
      const m = att.move;
      if (att.state !== "attack" || m === null || att.hitlag > 0) continue;
      const af = att.move_frame - m.startup;
      if (!(af >= 0 && af < m.active) || att.charging) continue;
      for (const tgt of this.fighters.values()) {
        if (tgt === att || att.hit_ids.has(tgt.pid) || !tgt.alive || tgt.invuln > 0
          || tgt.team === att.team) continue;
        const hurt = hurtboxRect(tgt.x, tgt.y, tgt.fdef.width, tgt.fdef.height);
        for (const hb of m.hitboxes) {
          if (!hitboxActive(hb, af)) continue;
          if (overlaps(hitboxRect(hb, att.x, att.y, att.facing), hurt)) {
            hits.push([att, tgt, hb]);
            break;
          }
        }
      }
    }
    for (const [att, tgt, hb] of hits) this.applyHit(att, tgt, hb);
  }

  applyHit(att, tgt, hb) {
    const m = att.move;
    const mult = m && m.charge ? 1.0 + C.CHARGE_BONUS * att.charge / m.charge : 1.0;
    const dmg = hb.dmg * mult;
    att.hit_ids.add(tgt.pid);
    tgt.damage = Math.min(C.MAX_DAMAGE, tgt.damage + dmg);
    att.dealt += dmg;
    const kb = knockback(hb, tgt.damage, tgt.fdef.weight, mult);
    let [vx, vy] = launchVector(hb.angle, kb, att.facing, axisX(tgt.prev_bits),
      axisY(tgt.prev_bits));
    if (tgt.grounded && vy < 0) vy = -vy * 0.5;
    tgt.vx = vx; tgt.vy = vy;
    if (vy > 0) tgt.grounded = false;
    tgt.state = "hitstun";
    tgt.hitstun = hitstunFrames(kb);
    tgt.move = null; tgt.charging = false; tgt.fastfall = false; tgt.recovery_used = false;
    tgt.jumps_left = Math.max(tgt.jumps_left, 1);
    tgt.last_hit_by = att.pid;
    const lag = hitlagFrames(dmg);
    att.hitlag = Math.max(att.hitlag, lag);
    tgt.hitlag = lag;
    this.events.push({ e: "hit", a: att.pid, t: tgt.pid, x: tgt.x,
      y: tgt.y + tgt.fdef.height / 2, dmg, kb });
  }

  spawn(f, invuln) {
    const [sx, sy] = this.stage.spawns[f.pid % this.stage.spawns.length];
    f.x = sx; f.y = sy; f.vx = 0.0; f.vy = 0.0;
    f.state = "air"; f.grounded = false; f.damage = 0.0;
    f.jumps_left = f.fdef.air_jumps; f.recovery_used = false; f.invuln = invuln;
    f.move = null; f.hitstun = 0; f.hitlag = 0; f.last_hit_by = null;
    f.facing = sx < 0 ? 1 : -1;
  }

  checkBlast(f) {
    if (!f.alive) return;
    const [left, rgt, bottom, tp] = this.stage.blast;
    if (left < f.x && f.x < rgt && bottom < f.y && f.y < tp) return;
    f.stocks -= 1;
    f.falls += 1;
    const killer = f.last_hit_by !== null ? this.fighters.get(f.last_hit_by) : undefined;
    if (killer) killer.kos += 1;
    this.events.push({ e: "ko", p: f.pid, x: f.x, y: f.y, by: f.last_hit_by });
    f.move = null; f.vx = 0.0; f.vy = 0.0;
    if (f.stocks > 0) { f.state = "ko"; f.respawn = C.RESPAWN_FRAMES; } else f.state = "out";
  }

  checkEnd() {
    const fs = [...this.fighters.values()];
    const alive = new Set(fs.filter((f) => f.stocks > 0).map((f) => f.team));
    const all = new Set(fs.map((f) => f.team));
    if (all.size > 1 && alive.size <= 1) {
      this.over = true;
      this.winner = alive.size ? [...alive][0] : null;
    } else if (this.frame >= this.maxFrames) {
      this.over = true;
      let best = fs[0];
      for (const f of fs) {
        if (f.stocks > best.stocks || (f.stocks === best.stocks && -f.damage > -best.damage)) {
          best = f;
        }
      }
      const tied = fs.some((f) => f.stocks === best.stocks && f.damage === best.damage
        && f.team !== best.team);
      this.winner = tied ? null : best.team;
    }
    if (this.over) this.events.push({ e: "end", winner: this.winner });
  }

  snapshot() {
    return { f: this.frame, over: this.over, winner: this.winner,
      fighters: [...this.fighters.values()].map(fighterState), events: this.events };
  }

  applySnapshot(snap, only = null) {
    this.frame = snap.f; this.over = snap.over; this.winner = snap.winner;
    for (const st of snap.fighters) {
      if (only === null || only.has(st.pid)) applyState(this.fighters.get(st.pid), st);
    }
  }
}
