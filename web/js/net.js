// Conexão com o servidor: mesmo protocolo msgpack/WebSocket do cliente desktop (client/net.py).
const { encode, decode } = window.MessagePack;
const RECONNECT_MS = 20000;

function store(key, value) {
  try {
    if (value === undefined) return sessionStorage.getItem(key);
    sessionStorage.setItem(key, value);
  } catch { /* armazenamento bloqueado: só não lembra o token */ }
  return null;
}

export class Net {
  constructor(name, password, version) {
    this.name = name;
    this.password = password;
    this.version = version;
    this.token = store("ringue-token") || "";
    this.playerId = null;
    this.phase = "lobby";
    this.lobby = {};
    this.gameStart = null;
    this.gameGen = 0;
    this.snapshots = [];
    this.connected = false;
    this.reconnecting = false;
    this.closing = false;
    this.error = null;
    this.ws = null;
  }

  url() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${location.host}/`;
  }

  connect() {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.url());
      ws.binaryType = "arraybuffer";
      let welcomed = false;
      ws.onopen = () => ws.send(encode({ t: "hello", name: this.name, token: this.token,
        password: this.password, version: this.version }));
      ws.onmessage = (ev) => {
        let msg;
        try { msg = decode(new Uint8Array(ev.data)); } catch { return; }
        if (!welcomed) {
          if (msg.t === "error") { reject(new Error(msg.reason || "recusado")); ws.close(); return; }
          if (msg.t === "welcome") {
            welcomed = true;
            this.ws = ws;
            this.connected = true;
            this.welcome(msg);
            resolve();
          }
          return;
        }
        this.handle(msg);
      };
      ws.onerror = () => { if (!welcomed) reject(new Error("não conectou ao servidor")); };
      ws.onclose = () => {
        if (!welcomed) { reject(new Error("conexão recusada")); return; }
        if (this.ws !== ws) return;
        this.connected = false;
        if (!this.closing && this.phase === "game" && this.token) this.reconnectLoop();
      };
    });
  }

  welcome(msg) {
    this.playerId = msg.player_id;
    this.token = msg.token;
    this.phase = msg.phase;
    store("ringue-token", this.token);
  }

  handle(msg) {
    switch (msg.t) {
      case "snapshot": this.snapshots.push(msg); break;
      case "lobby": this.lobby = msg; this.phase = msg.phase; break;
      case "game_start":
        this.snapshots = [];
        this.gameStart = msg;
        this.phase = "game";
        this.gameGen += 1;
        break;
      case "welcome": this.welcome(msg); break;
      case "error": this.error = msg.reason; break;
      default: break;
    }
  }

  async reconnectLoop() {
    this.reconnecting = true;
    const deadline = performance.now() + RECONNECT_MS;
    while (performance.now() < deadline && !this.closing) {
      try {
        await this.connect();
        this.reconnecting = false;
        return;
      } catch {
        await new Promise((r) => setTimeout(r, 1000));
      }
    }
    this.reconnecting = false;
    this.error = "conexão perdida";
  }

  send(t, fields = {}) {
    if (!this.connected || !this.ws) return;
    try { this.ws.send(encode({ t, ...fields })); } catch { /* caiu: onclose cuida */ }
  }

  me() {
    return (this.lobby.players || []).find((p) => p.id === this.playerId) || null;
  }

  isHost() { return this.lobby.host === this.playerId; }

  close() {
    this.closing = true;
    this.send("leave");
    if (this.ws) this.ws.close();
    this.connected = false;
  }
}
