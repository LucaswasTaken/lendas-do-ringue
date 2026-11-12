// Partida online no navegador: port de client/drivers.py (NetDriver).
// O próprio lutador é previsto (stepOne + reconciliação pelo ack); os outros são
// interpolados INTERP_FRAMES no passado.
import { C, World, applyState } from "./sim.js";

const PREDICTED = new Set(["jump", "dodge", "attack"]);

export class NetDriver {
  constructor(net, content, readBits) {
    this.net = net;
    this.readBits = readBits;
    const gs = net.gameStart;
    this.gen = net.gameGen;
    this.roster = new Map(gs.roster.map((r) => [r.pid, r]));
    this.world = new World(content.stages[gs.stage],
      gs.roster.map((r) => [r.pid, content.fighters[r.fighter]]),
      { stocks: gs.stocks, seconds: gs.seconds });
    this.me = net.playerId;
    this.seq = 0;
    this.pending = [];
    this.snaps = [];
    this.sinceLatest = 0;
    this.err = [0, 0];
    this.finished = false;
  }

  tick() {
    const events = this.drain();
    const net = this.net;
    const lost = !net.connected && !net.reconnecting;
    if (lost || net.phase === "lobby" || net.gameGen !== this.gen) {
      this.finished = true;
      return events;
    }
    if (!net.connected) return events;
    const bits = this.readBits();
    this.seq += 1;
    this.pending.push([this.seq, bits]);
    if (this.pending.length > 120) this.pending.shift();
    net.send("input", { inputs: this.pending.slice(-C.INPUT_REDUNDANCY) });
    if (this.world.fighters.has(this.me)) {
      this.world.events = [];
      this.world.stepOne(this.me, bits);
      for (const e of this.world.events) if (PREDICTED.has(e.e)) events.push(e);
    }
    this.sinceLatest += 1;
    this.placeOthers();
    this.err[0] *= 0.85;
    this.err[1] *= 0.85;
    return events;
  }

  drain() {
    const events = [];
    const incoming = this.net.snapshots;
    this.net.snapshots = [];
    for (const snap of incoming) {
      this.snaps.push(snap);
      if (this.snaps.length > 40) this.snaps.shift();
      this.sinceLatest = 0;
      for (const e of snap.events || []) {
        if (PREDICTED.has(e.e) && e.p === this.me) continue;
        events.push(e);
      }
      this.reconcile(snap);
    }
    return events;
  }

  reconcile(snap) {
    const w = this.world;
    w.frame = snap.f; w.over = snap.over; w.winner = snap.winner;
    const mine = snap.fighters.find((s) => s.pid === this.me);
    if (!mine) return;
    const f = w.fighters.get(this.me);
    const bx = f.x, by = f.y;
    if (snap.ack !== null && snap.ack !== undefined) {
      while (this.pending.length && this.pending[0][0] <= snap.ack) this.pending.shift();
    }
    applyState(f, mine);
    w.events = [];
    for (const [, bits] of this.pending) w.stepOne(this.me, bits);
    w.events = [];
    const dx = bx - f.x, dy = by - f.y;
    if (Math.hypot(dx, dy) < 160) { this.err[0] += dx; this.err[1] += dy; } else this.err = [0, 0];
  }

  placeOthers() {
    const snaps = this.snaps;
    if (!snaps.length) return;
    const renderF = snaps[snaps.length - 1].f + this.sinceLatest - C.INTERP_FRAMES;
    let i = -1;
    for (let k = snaps.length - 1; k >= 0; k--) if (snaps[k].f <= renderF) { i = k; break; }
    let a, b;
    if (i < 0) { a = b = snaps[0]; } else if (i === snaps.length - 1) { a = b = snaps[i]; } else {
      a = snaps[i]; b = snaps[i + 1];
    }
    const t = b.f > a.f ? Math.max(0, Math.min(1, (renderF - a.f) / (b.f - a.f))) : 0;
    const bBy = new Map(b.fighters.map((s) => [s.pid, s]));
    for (const sa of a.fighters) {
      if (sa.pid === this.me) continue;
      const sb = bBy.get(sa.pid) || sa;
      const f = this.world.fighters.get(sa.pid);
      applyState(f, t > 0.5 ? sb : sa);
      if (Math.abs(sb.x - sa.x) + Math.abs(sb.y - sa.y) < 400) {
        f.x = sa.x + (sb.x - sa.x) * t;
        f.y = sa.y + (sb.y - sa.y) * t;
      }
    }
  }

  label(pid) {
    const r = this.roster.get(pid);
    const name = r ? r.name : `P${pid + 1}`;
    return pid === this.me ? `${name} (você)` : name;
  }

  offset(pid) { return pid === this.me ? this.err : [0, 0]; }
}
