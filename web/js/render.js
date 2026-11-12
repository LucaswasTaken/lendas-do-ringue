// Desenho no canvas: palco, lutadores (port de client/rig.py), partículas e HUD.
import { C, hitboxActive, hitboxRect } from "./sim.js";

const TAG_COLORS = [[255, 90, 90], [90, 160, 255], [120, 230, 120], [255, 210, 80]];
const HEAVY_PREFIX = ["heavy_", "air_heavy", "recovery"];
const REST_ARMS = [-100, -70, -80, -100];
const rgba = (c, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const shade = (c, k) => c.map((v) => Math.max(0, Math.min(255, Math.round(v * k))));
const lerp = (a, b, t) => a + (b - a) * t;
const rad = (d) => d * Math.PI / 180;

// ------------------------------------------------------------------ pose (= client/rig.py)
function pose(f, frame) {
  const st = f.state;
  const P = (o) => ({ crouch: 0, lean: 0, legs: [-95, -90, -85, -90], arms: [-100, -80, -80, -95],
    weapon: 0, ...o });
  if (st === "ledge") return P({ legs: [-100, -95, -80, -90], arms: [78, 85, 95, 90] });
  if (st === "hitstun") {
    const wob = Math.sin(frame * 0.9) * 25;
    return P({ lean: -28, legs: [-60 + wob, -120, -135, -100 - wob],
      arms: [130 + wob, 160, 60 - wob, 30], weapon: 40 });
  }
  if (st === "dodge") {
    return P({ crouch: 0.35, lean: 25, legs: [-60, -110, -120, -80], arms: [-60, -20, -120, -90] });
  }
  if (st === "land") return P({ crouch: 0.4, lean: 12, legs: [-50, -115, -125, -70] });
  if (st === "attack" && f.move) return attackPose(f, frame);
  if (!f.grounded) {
    if (f.vy > 0) return P({ legs: [-35, -105, -70, -125], arms: [-40, -10, -140, -110], lean: 5 });
    return P({ legs: [-100, -95, -78, -100], arms: [-20, 10, -150, -130] });
  }
  if (st === "run" || Math.abs(f.vx) > 60) {
    const s = Math.sin(frame * 0.32 * f.fdef.speed);
    const ft = -90 + 38 * s, bt = -90 - 38 * s;
    return P({ lean: 14, legs: [ft, ft - 25 - 25 * Math.max(0, -s), bt, bt - 25 - 25 * Math.max(0, s)],
      arms: [-90 - 40 * s, -60 - 40 * s, -90 + 40 * s, -60 + 40 * s], weapon: 80 });
  }
  const breath = Math.sin(frame * 0.08) * 3;
  return P({ crouch: 0.04 + breath * 0.004, legs: [-100, -88, -78, -92],
    arms: [-105 + breath, -55, -75 - breath, -100], weapon: 105 });
}

function attackPose(f, frame) {
  const m = f.move, key = m.key, h = f.fdef.height;
  const hb = m.hitboxes[0];
  const aim = Math.atan2(hb.y - h * 0.72, Math.max(hb.x, 1)) * 180 / Math.PI;
  const heavy = HEAVY_PREFIX.some((p) => key.startsWith(p));
  const windup = aim + (heavy ? 150 : 105);
  const mf = f.move_frame;
  let arm, weapon = 0;
  if (mf < m.startup) {
    let a = lerp(REST_ARMS[0], windup, Math.min(1, ((mf + 1) / m.startup) * 1.4));
    if (f.charging) a = windup + Math.sin(frame * 1.7) * 4;
    arm = [a, a + 25, -60, -100];
    weapon = 30;
  } else if (mf < m.startup + m.active) {
    arm = [aim, aim, -150, -120];
  } else {
    const t = (mf - m.startup - m.active) / Math.max(1, m.recovery);
    const a = lerp(aim - 25, REST_ARMS[0], t);
    arm = [a, lerp(aim - 10, REST_ARMS[1], t), -110, -100];
  }
  let legs = [-75, -100, -120, -85], crouch = 0.05, lean = 10;
  if (key.endsWith("_down") && f.grounded) { crouch = 0.4; lean = 20; legs = [-40, -120, -140, -60]; }
  else if (key === "air_down" || key === "air_heavy_down") { legs = [-95, -95, -85, -85]; lean = -5; }
  else if (!f.grounded) legs = [-40, -110, -80, -120];
  if (key === "recovery") lean = -5;
  return { crouch, lean, legs, arms: arm, weapon };
}

// ------------------------------------------------------------------ esqueleto (coords de mundo)
const pt = (o, ang, len, fc) => [o[0] + Math.cos(rad(ang)) * len * fc, o[1] + Math.sin(rad(ang)) * len];

function line(ctx, a, b, color, width) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
}
function limb(ctx, a, b, w, color, alpha) {
  line(ctx, a, b, `rgba(20,20,30,${alpha})`, w + 4);
  line(ctx, a, b, rgba(color, alpha), w);
}
function circle(ctx, x, y, r, fill) {
  ctx.fillStyle = fill; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
}

export function drawFighter(ctx, f, x, y, frame, alpha, tint) {
  const fd = f.fdef, h = fd.height, fc = f.facing;
  const p = pose(f, frame);
  const color = tint || fd.color;
  const back = shade(color, 0.68);
  const lw = Math.max(6, h * 0.085);
  ctx.lineCap = "round";
  const hip = [x, y + h * (0.47 - 0.2 * p.crouch)];
  const torso = 90 - p.lean;
  const neck = pt(hip, torso, h * 0.31, fc);
  const shoulder = pt(hip, torso, h * 0.27, fc);
  const head = pt(hip, torso, h * 0.43, fc);
  const leg = (ta, sa, col) => {
    const knee = pt(hip, ta, h * 0.25, fc), foot = pt(knee, sa, h * 0.24, fc);
    limb(ctx, hip, knee, lw, col, alpha); limb(ctx, knee, foot, lw * 0.9, col, alpha);
  };
  const arm = (ua, fa, col, weapon) => {
    const elbow = pt(shoulder, ua, h * 0.17, fc), hand = pt(elbow, fa, h * 0.16, fc);
    if (weapon) drawWeapon(ctx, fd.weapon, hand, fa + p.weapon, h, fc, fd.accent, alpha);
    limb(ctx, shoulder, elbow, lw * 0.8, col, alpha); limb(ctx, elbow, hand, lw * 0.75, col, alpha);
  };
  arm(p.arms[2], p.arms[3], back, false);
  leg(p.legs[2], p.legs[3], back);
  line(ctx, hip, neck, `rgba(20,20,30,${alpha})`, lw * 1.7 + 4);
  line(ctx, hip, neck, rgba(color, alpha), lw * 1.7);
  const belt = pt(hip, torso, h * 0.03, fc);
  circle(ctx, belt[0], belt[1], lw * 0.7, rgba(shade(fd.accent, 0.8), alpha));
  leg(p.legs[0], p.legs[1], color);
  const r = h * 0.105;
  circle(ctx, head[0], head[1], r + 2, `rgba(20,20,30,${alpha})`);
  circle(ctx, head[0], head[1], r, `rgba(240,210,180,${alpha})`);
  ctx.fillStyle = rgba(fd.hair, alpha); // cabelo: meia elipse em cima
  ctx.beginPath();
  ctx.ellipse(head[0], head[1] + r * 0.15, r * 1.1, r, 0, 0, Math.PI);
  ctx.fill();
  circle(ctx, head[0] + fc * r * 0.45, head[1], Math.max(2, r * 0.18), `rgba(20,20,30,${alpha})`);
  arm(p.arms[0], p.arms[1], color, true);
}

function drawWeapon(ctx, kind, hand, ang, h, fc, accent, alpha) {
  const metal = `rgba(205,212,228,${alpha})`, wood = `rgba(120,80,50,${alpha})`;
  const dark = `rgba(20,20,30,${alpha})`;
  if (kind === "sword") {
    const tip = pt(hand, ang, h * 0.5, fc);
    line(ctx, hand, tip, dark, 9); line(ctx, hand, tip, metal, 5);
    line(ctx, pt(hand, ang + 90, h * 0.07, fc), pt(hand, ang - 90, h * 0.07, fc), rgba(accent, alpha), 5);
  } else if (kind === "hammer") {
    const end = pt(hand, ang, h * 0.48, fc), start = pt(hand, ang, -h * 0.08, fc);
    line(ctx, start, end, dark, 9); line(ctx, start, end, wood, 5);
    const a = pt(end, ang + 90, h * 0.13, fc), b = pt(end, ang - 90, h * 0.13, fc);
    ctx.lineCap = "butt";
    line(ctx, a, b, dark, h * 0.17 + 4); line(ctx, a, b, rgba(accent, alpha), h * 0.17);
    ctx.lineCap = "round";
  } else if (kind === "spear") {
    const start = pt(hand, ang, -h * 0.3, fc), end = pt(hand, ang, h * 0.62, fc);
    line(ctx, start, end, dark, 8); line(ctx, start, end, wood, 4);
    const tip = pt(end, ang, h * 0.16, fc);
    const sa = pt(end, ang + 90, h * 0.05, fc), sb = pt(end, ang - 90, h * 0.05, fc);
    ctx.fillStyle = metal;
    ctx.beginPath(); ctx.moveTo(...tip); ctx.lineTo(...sa); ctx.lineTo(...sb); ctx.fill();
  } else {
    for (const off of [-18, 0, 18]) {
      const tip = pt(hand, ang + off, h * 0.17, fc);
      line(ctx, hand, tip, dark, 6); line(ctx, hand, tip, rgba(accent, alpha), 3);
    }
  }
}

// ------------------------------------------------------------------ efeitos
export class Effects {
  constructor() { this.parts = []; this.shake = 0; }
  burst(x, y, color, n, speed, life, size) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2, s = speed * (0.3 + 0.7 * Math.random());
      const lf = life * (0.5 + 0.5 * Math.random());
      this.parts.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: lf, max: lf,
        size: size * (0.5 + 0.5 * Math.random()), color });
    }
  }
  onEvent(ev, colors) {
    if (ev.e === "hit") {
      const strong = ev.kb > 1200;
      this.burst(ev.x, ev.y, [255, 240, 160], strong ? 22 : 10, strong ? 900 : 500, 0.35,
        strong ? 9 : 6);
      this.shake = Math.max(this.shake, Math.min(26, ev.kb / 90));
    } else if (ev.e === "ko") {
      this.burst(ev.x, ev.y, colors.get(ev.p) || [255, 255, 255], 60, 1600, 0.9, 14);
      this.shake = 30;
    } else if (ev.e === "jump" && ev.air) this.burst(ev.x, ev.y, [200, 200, 220], 6, 200, 0.25, 5);
    else if (ev.e === "dodge") this.burst(ev.x, ev.y + 50, [170, 210, 255], 8, 250, 0.3, 6);
  }
  update(dt) {
    for (const p of this.parts) {
      p.life -= dt; p.x += p.vx * dt; p.y += p.vy * dt; p.vx *= 0.9; p.vy = p.vy * 0.9 - 600 * dt;
    }
    this.parts = this.parts.filter((p) => p.life > 0);
    this.shake = Math.max(0, this.shake - 60 * dt);
  }
  draw(ctx) {
    for (const p of this.parts) {
      const k = p.life / p.max, s = p.size * (0.4 + 0.6 * k);
      ctx.fillStyle = rgba(p.color, k);
      ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s);
    }
  }
}

// ------------------------------------------------------------------ cena
export class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.cam = { x: 0, y: 150, zoom: 0.7 };
    this.fx = new Effects();
    this.showBoxes = false;
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const c = this.canvas;
    const w = Math.round(c.clientWidth * dpr), h = Math.round(c.clientHeight * dpr);
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    return dpr;
  }

  updateCamera(world, dt) {
    const W = this.canvas.width, H = this.canvas.height;
    const alive = [...world.fighters.values()].filter((f) => f.alive);
    const xs = [0, ...alive.map((f) => f.x)], ys = [-60, ...alive.map((f) => f.y + 60)];
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const hud = 120 * (window.devicePixelRatio || 1);
    let zoom = Math.min(W / (maxX - minX + 700), (H - hud) / (maxY - minY + 420));
    zoom = Math.max(0.3 * (window.devicePixelRatio || 1), Math.min(1.15 * (window.devicePixelRatio || 1), zoom));
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2 - hud / 2 / zoom;
    const k = Math.min(1, dt * 5);
    this.cam.x += (cx - this.cam.x) * k;
    this.cam.y += (cy - this.cam.y) * k;
    this.cam.zoom += (zoom - this.cam.zoom) * k;
  }

  toScreen(x, y) {
    const { x: cx, y: cy, zoom } = this.cam;
    return [(x - cx) * zoom + this.canvas.width / 2, this.canvas.height / 2 - (y - cy) * zoom];
  }

  draw(world, driver, prev, alpha) {
    const ctx = this.ctx, W = this.canvas.width, H = this.canvas.height;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = rgba(world.stage.background);
    ctx.fillRect(0, 0, W, H);
    const sh = this.fx.shake;
    const ox = (Math.random() * 2 - 1) * sh, oy = (Math.random() * 2 - 1) * sh;
    const { x: cx, y: cy, zoom } = this.cam;
    ctx.setTransform(zoom, 0, 0, -zoom, W / 2 - (cx + ox) * zoom, H / 2 + (cy + oy) * zoom);
    this.drawStage(ctx, world.stage);
    const tags = [];
    for (const f of world.fighters.values()) {
      if (!f.alive) continue;
      const pp = prev.get(f.pid) || [f.x, f.y];
      const off = driver.offset(f.pid);
      const x = pp[0] + (f.x - pp[0]) * alpha + off[0];
      const y = pp[1] + (f.y - pp[1]) * alpha + off[1];
      let a = 1;
      if (f.invuln > 0 && Math.floor(world.frame / 4) % 2 === 0) a = 0.45;
      if (f.state === "dodge") a = 0.47;
      if (f.grounded) {
        ctx.fillStyle = "rgba(0,0,0,0.27)";
        ctx.beginPath(); ctx.ellipse(x, y + 2, f.fdef.width * 0.65, 6, 0, 0, Math.PI * 2); ctx.fill();
      }
      if (f.charging) {
        ctx.strokeStyle = "rgba(255,220,100,0.67)"; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(x, y + f.fdef.height / 2, f.fdef.width / 2 + 10 + f.charge, 0,
          Math.PI * 2); ctx.stroke();
      }
      const tint = f.state === "hitstun" ? f.fdef.color.map((c) => Math.min(255, c + 90)) : null;
      drawFighter(ctx, f, x, y, world.frame, a, tint);
      if (this.showBoxes) this.drawBoxes(ctx, f, x, y);
      tags.push([f.pid, x, y + f.fdef.height + 14]);
    }
    this.fx.draw(ctx);
    // textos em coordenadas de tela
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.textAlign = "center";
    ctx.font = `bold ${12 * dpr}px system-ui, sans-serif`;
    for (const [pid, x, y] of tags) {
      const [sx, sy] = this.toScreen(x, y);
      ctx.fillStyle = rgba(TAG_COLORS[pid % 4]);
      ctx.fillText(driver.label(pid), sx, sy - 6 * dpr);
    }
    this.drawHud(ctx, world, driver, W, H, dpr);
  }

  drawStage(ctx, stage) {
    const [l, r, b, t] = stage.blast;
    ctx.strokeStyle = "rgba(255,255,255,0.1)"; ctx.lineWidth = 4;
    ctx.strokeRect(l, b, r - l, t - b);
    for (const p of stage.platforms) {
      const top = p.y + p.h;
      if (p.soft) {
        ctx.fillStyle = "rgb(150,140,190)"; ctx.fillRect(p.x, p.y, p.w, p.h);
        ctx.fillStyle = "rgb(210,200,250)"; ctx.fillRect(p.x, top - 4, p.w, 4);
      } else {
        ctx.fillStyle = "rgb(70,64,92)"; ctx.fillRect(p.x, p.y, p.w, p.h);
        ctx.fillStyle = "rgb(120,170,110)"; ctx.fillRect(p.x, top - 14, p.w, 14);
        ctx.fillStyle = "rgb(60,100,60)"; ctx.fillRect(p.x, top - 18, p.w, 4);
      }
    }
  }

  drawBoxes(ctx, f, x, y) {
    const m = f.move;
    if (!m || f.state !== "attack" || f.charging) return;
    const af = f.move_frame - m.startup;
    if (af < 0 || af >= m.active) return;
    ctx.fillStyle = "rgba(255,60,60,0.43)";
    for (const hb of m.hitboxes) {
      if (!hitboxActive(hb, af)) continue;
      const [l, r, b, t] = hitboxRect(hb, x, y, f.facing);
      ctx.fillRect(l, b, r - l, t - b);
    }
  }

  drawHud(ctx, world, driver, W, H, dpr) {
    const secs = Math.floor(world.timeLeft);
    ctx.fillStyle = "#fff";
    ctx.font = `bold ${22 * dpr}px system-ui, sans-serif`;
    ctx.fillText(`${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`, W / 2, 40 * dpr);
    const fs = [...world.fighters.values()];
    const slot = Math.min(260 * dpr, W / Math.max(1, fs.length));
    const start = W / 2 - (slot * fs.length) / 2;
    fs.forEach((f, i) => {
      const cx = start + slot * (i + 0.5);
      ctx.fillStyle = "rgba(10,10,18,0.75)";
      ctx.fillRect(cx - slot / 2 + 8 * dpr, H - 104 * dpr, slot - 16 * dpr, 90 * dpr);
      ctx.fillStyle = rgba(TAG_COLORS[f.pid % 4]);
      ctx.fillRect(cx - slot / 2 + 8 * dpr, H - 104 * dpr, slot - 16 * dpr, 4 * dpr);
      ctx.fillStyle = "rgb(220,220,230)";
      ctx.font = `${12 * dpr}px system-ui, sans-serif`;
      ctx.fillText(`${driver.label(f.pid)} · ${f.fdef.name}`, cx, H - 80 * dpr);
      ctx.font = `bold ${30 * dpr}px system-ui, sans-serif`;
      if (f.state === "out") {
        ctx.fillStyle = "rgb(130,130,140)"; ctx.fillText("FORA", cx, H - 40 * dpr);
      } else {
        ctx.fillStyle = rgba(damageColor(f.damage));
        ctx.fillText(`${Math.floor(f.damage)}%`, cx, H - 40 * dpr);
      }
      for (let s = 0; s < f.stocks; s++) {
        circle(ctx, cx - (f.stocks - 1) * 9 * dpr + s * 18 * dpr, H - 24 * dpr, 6 * dpr,
          rgba(f.fdef.color));
      }
    });
    if (world.over) {
      ctx.fillStyle = "rgba(0,0,0,0.67)"; ctx.fillRect(0, 0, W, H);
      const win = world.winner;
      const msg = win === null ? "EMPATE!"
        : `${driver.label(win)} (${world.fighters.get(win).fdef.name}) VENCEU!`;
      ctx.fillStyle = "rgb(255,220,120)";
      ctx.font = `bold ${36 * dpr}px system-ui, sans-serif`;
      ctx.fillText(msg, W / 2, H / 2 - 60 * dpr);
      ctx.font = `${16 * dpr}px system-ui, sans-serif`;
      ctx.fillStyle = "#fff";
      [...fs].sort((a, b) => b.kos - a.kos || a.falls - b.falls).forEach((f, i) => {
        ctx.fillText(`${driver.label(f.pid)} · ${f.fdef.name}: ${f.kos} KOs · ${f.falls} quedas`,
          W / 2, H / 2 + (i * 28 - 10) * dpr);
      });
      ctx.fillStyle = "rgb(200,200,210)";
      ctx.fillText("voltando para a sala…", W / 2, H / 2 + 130 * dpr);
    }
  }
}

function damageColor(d) {
  const t = Math.min(1, d / 150);
  if (t < 0.5) return [255, 255, Math.round(255 * (1 - t / 0.5))];
  const k = (t - 0.5) / 0.5;
  return [255 - Math.round(80 * k), Math.round(255 * (1 - k)), 0];
}

export { TAG_COLORS, C };
