// Cliente de navegador: entrar na sala do servidor que serviu esta página, sala e partida.
import { Audio } from "./audio.js";
import { NetDriver } from "./driver.js";
import { clearHeld, installInput, readBits } from "./input.js";
import { Net } from "./net.js";
import { Renderer } from "./render.js";
import { C, configure } from "./sim.js";

const $ = (id) => document.getElementById(id);
const audio = new Audio();
let content = null;
let net = null;
let driver = null;
let shownGen = 0; // última partida já mostrada (para não reabrir a mesma)

function show(id) {
  for (const s of ["menu", "lobby"]) $(s).classList.toggle("hidden", s !== id);
}

function storeGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function storeSet(k, v) { try { localStorage.setItem(k, v); } catch { /* ok */ } }

// ------------------------------------------------------------------ entrar
async function boot() {
  installInput();
  for (const ev of ["keydown", "pointerdown"]) window.addEventListener(ev, () => audio.unlock());
  window.addEventListener("keydown", (e) => {
    if (e.target instanceof HTMLInputElement) return;
    if (e.code === "KeyM") audio.toggleMute();
    if (e.code === "F1" && renderer) { e.preventDefault(); renderer.showBoxes = !renderer.showBoxes; }
  });
  try {
    content = await (await fetch("/api/content.json")).json();
    configure(content.constants);
    const info = await (await fetch("/api/info")).json();
    $("pw-row").classList.toggle("hidden", !info.password);
  } catch (e) {
    $("loading").textContent = "Não consegui falar com o servidor.";
    return;
  }
  $("loading").classList.add("hidden");
  $("name").value = storeGet("ringue-name") || `Lutador${100 + Math.floor(Math.random() * 900)}`;
  $("join-form").addEventListener("submit", (e) => { e.preventDefault(); join(); });
  $("practice").addEventListener("click", () => join(true));
  setupLobby();
  show("menu");
  audio.music("menu");
  requestAnimationFrame(frame);
  if (new URLSearchParams(location.search).has("treino")) join(true);
}

// Treino: entra e, se for o anfitrião de uma sala vazia, põe um bot e começa.
async function practice() {
  const wait = (cond) => new Promise((res) => {
    const end = performance.now() + 4000;
    const poll = () => (cond() || performance.now() > end ? res(cond()) : setTimeout(poll, 50));
    poll();
  });
  if (!(await wait(() => (net.lobby.players || []).length > 0))) return;
  if (!net.isHost() || net.lobby.players.length > 1) return;
  net.send("add_bot");
  if (await wait(() => net.lobby.can_start)) net.send("start");
}

async function join(training = false) {
  const name = $("name").value.trim().slice(0, 16) || "Lutador";
  storeSet("ringue-name", name);
  $("menu-error").textContent = "";
  const n = new Net(name, $("password").value, content.protocol_version);
  try {
    await n.connect();
  } catch (e) {
    $("menu-error").textContent = `Não conectou: ${e.message}`;
    return;
  }
  net = n;
  shownGen = net.phase === "game" ? 0 : net.gameGen;
  show("lobby");
  if (training) practice();
}

// ------------------------------------------------------------------ sala
function setupLobby() {
  const fsel = $("fighter"), ssel = $("stage");
  for (const [k, f] of Object.entries(content.fighters)) fsel.add(new Option(f.name, k));
  for (const [k, s] of Object.entries(content.stages)) ssel.add(new Option(s.name, k));
  fsel.addEventListener("change", () => net && net.send("pick", { fighter: fsel.value }));
  ssel.addEventListener("change", () => net && net.send("stage", { stage: ssel.value }));
  $("bot-level").addEventListener("change",
    () => net && net.send("bots", { level: $("bot-level").value }));
  $("ready").addEventListener("click", () => {
    const me = net && net.me();
    if (me) net.send("ready", { ready: !me.ready });
  });
  $("add-bot").addEventListener("click", () => net && net.send("add_bot"));
  $("remove-bot").addEventListener("click", () => net && net.send("remove_bot"));
  $("start").addEventListener("click", () => net && net.send("start"));
  $("leave").addEventListener("click", leave);
}

function leave() {
  if (net) net.close();
  net = null;
  driver = null;
  show("menu");
  audio.music("menu");
}

let lastLobbyKey = "";
function renderLobby() {
  const lb = net.lobby;
  const key = JSON.stringify(lb);
  if (key === lastLobbyKey) return;
  lastLobbyKey = key;
  const ul = $("players");
  ul.textContent = "";
  for (const p of lb.players || []) {
    const li = document.createElement("li");
    if (p.id === net.playerId) li.classList.add("me");
    const sw = document.createElement("span");
    sw.className = "swatch";
    const fd = content.fighters[p.fighter];
    sw.style.background = fd ? `rgb(${fd.color.join(",")})` : "#888";
    const name = document.createElement("span");
    const host = p.id === lb.host ? " (anfitrião)" : "";
    name.textContent = `${p.name}${host} · ${fd ? fd.name : p.fighter}`;
    const tag = document.createElement("span");
    const ok = p.bot || p.ready || p.id === lb.host;
    tag.className = `tag${ok ? " ok" : ""}`;
    tag.textContent = p.bot ? "BOT" : ok ? "PRONTO" : "esperando";
    li.append(sw, name, tag);
    ul.append(li);
  }
  const me = net.me();
  const host = net.isHost();
  if (me) $("fighter").value = me.fighter;
  $("stage").value = lb.stage || "";
  $("bot-level").value = lb.bot_level || "medio";
  $("host-controls").classList.toggle("hidden", !host);
  $("ready").classList.toggle("hidden", host);
  $("ready").textContent = me && me.ready ? "Não estou pronto" : "Pronto";
  $("start").disabled = !lb.can_start;
  $("lobby-status").textContent = lb.notice || (host
    ? (lb.can_start ? "Pode iniciar!" : "Precisa de 2+ lutadores e todos prontos.")
    : "Esperando o anfitrião iniciar.");
}

// ------------------------------------------------------------------ partida
let renderer = null;
let acc = 0;
let lastT = performance.now();
let prev = new Map();

function frame(t) {
  const dt = Math.min(0.25, (t - lastT) / 1000);
  lastT = t;
  if (net) {
    $("reconnect").classList.toggle("hidden", !net.reconnecting);
    if (!net.connected && !net.reconnecting) {
      const err = net.error || "conexão perdida";
      leave();
      $("menu-error").textContent = err;
    } else if (!driver && net.phase === "game" && net.gameStart && net.gameGen !== shownGen) {
      startGame();
    } else if (!driver) {
      renderLobby();
    }
  }
  if (driver) tickGame(dt);
  requestAnimationFrame(frame);
}

function startGame() {
  shownGen = net.gameGen;
  clearHeld();
  driver = new NetDriver(net, content, readBits);
  renderer = renderer || new Renderer($("game"));
  prev = new Map();
  acc = 0;
  for (const s of ["menu", "lobby"]) $(s).classList.add("hidden");
  audio.music("fight");
}

function tickGame(dt) {
  const r = renderer;
  r.resize();
  acc += dt;
  const step = 1 / C.TICK_RATE;
  while (acc >= step && driver) {
    acc -= step;
    prev = new Map([...driver.world.fighters.values()].map((f) => [f.pid, [f.x, f.y]]));
    for (const ev of driver.tick()) {
      r.fx.onEvent(ev, new Map([...driver.world.fighters.values()].map((f) => [f.pid, f.fdef.color])));
      audio.onEvent(ev, ((ev.x ?? r.cam.x) - r.cam.x) / 900);
    }
    if (driver.finished) {
      const reconnected = net && net.connected && net.phase === "game" && net.gameGen !== driver.gen;
      driver = null;
      if (reconnected) { startGame(); return; }
      if (net) { show("lobby"); lastLobbyKey = ""; audio.music("menu"); }
      return;
    }
  }
  r.fx.update(dt);
  r.updateCamera(driver.world, dt);
  r.draw(driver.world, driver, prev, acc / step);
}

// gancho para depuração no console do navegador (ex.: ringue.driver.world)
window.ringue = { get net() { return net; }, get driver() { return driver; } };

boot();
