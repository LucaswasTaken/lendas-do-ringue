// Som no navegador (Web Audio): mesmos .wav gerados por tools/build_audio.py.
// O navegador só libera áudio depois de um clique/tecla: unlock() é chamado nesses eventos.
const HEAVY_PREFIX = ["heavy_", "recovery", "air_heavy_down"];
const MIN_GAP = { hit: 40, swing: 40 };

export class Audio {
  constructor() {
    this.ctx = null;
    this.buffers = new Map();
    this.last = new Map();
    this.muted = false;
    this.musicName = null;
    this.musicNode = null;
    this.wantMusic = null;
  }

  unlock() {
    if (!this.ctx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      this.ctx = new Ctx();
      this.master = this.ctx.createGain();
      this.master.gain.value = 0.6;
      this.master.connect(this.ctx.destination);
      if (this.wantMusic) this.music(this.wantMusic, true);
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
  }

  async load(path) {
    if (this.buffers.has(path)) return this.buffers.get(path);
    const p = fetch(path).then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(r.status))))
      .then((b) => this.ctx.decodeAudioData(b)).catch(() => null);
    this.buffers.set(path, p);
    return p;
  }

  async play(name, volume = 1, pan = 0) {
    if (!this.ctx || this.muted) return;
    const now = performance.now();
    if (now - (this.last.get(name) || 0) < (MIN_GAP[name] || 0)) return;
    this.last.set(name, now);
    const buf = await this.load(`/assets/sounds/${name}.wav`);
    if (!buf) return;
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    const g = this.ctx.createGain();
    g.gain.value = volume;
    let node = g;
    if (this.ctx.createStereoPanner) {
      const p = this.ctx.createStereoPanner();
      p.pan.value = Math.max(-1, Math.min(1, pan));
      g.connect(p);
      node = p;
    }
    node.connect(this.master);
    src.connect(g);
    src.start();
  }

  onEvent(ev, pan) {
    switch (ev.e) {
      case "jump": this.play(ev.air ? "airjump" : "jump", 0.6, pan); break;
      case "attack":
        this.play(HEAVY_PREFIX.some((p) => ev.m.startsWith(p)) ? "swing_heavy" : "swing", 0.7, pan);
        break;
      case "hit": this.play(ev.kb > 1100 ? "hit_heavy" : "hit", 1, pan); break;
      case "ko": this.play("ko", 1, pan); break;
      case "dodge": this.play("dodge", 0.6, pan); break;
      case "ledge": this.play("ledge", 0.6, pan); break;
      case "end": this.music(null); this.play("victory", 0.9); break;
      default: break;
    }
  }

  async music(name, force = false) {
    this.wantMusic = name;
    if (!this.ctx || (name === this.musicName && !force)) return;
    if (this.musicNode) { try { this.musicNode.stop(); } catch { /* já parou */ } }
    this.musicNode = null;
    this.musicName = name;
    if (!name || this.muted) return;
    const buf = await this.load(`/assets/music/${name}.wav`);
    if (!buf || this.musicName !== name) return;
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    const g = this.ctx.createGain();
    g.gain.value = 0.35;
    src.connect(g).connect(this.master);
    src.start();
    this.musicNode = src;
  }

  toggleMute() {
    this.muted = !this.muted;
    if (this.muted) {
      const want = this.wantMusic;
      this.music(null);
      this.wantMusic = want;
    } else {
      this.music(this.wantMusic, true);
    }
  }
}
