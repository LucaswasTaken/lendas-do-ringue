// Roda o cliente de navegador (web/js) no Node contra um servidor de verdade:
// conecta, põe um bot, inicia, joga ~3 s com predição e desenha cada quadro num canvas falso.
// Uso: node web_client_smoke.mjs <host:porta>   -> imprime JSON com estatísticas.
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = (p) => pathToFileURL(resolve(here, "../web/js", p)).href;
const require = createRequire(import.meta.url);
const host = process.argv[2];

globalThis.window = { MessagePack: require(resolve(here, "../web/vendor/msgpack.min.js")),
  devicePixelRatio: 1 };
globalThis.location = { protocol: "http:", host };

const sim = await import(web("sim.js"));
const { Net } = await import(web("net.js"));
const { NetDriver } = await import(web("driver.js"));
const { Renderer } = await import(web("render.js"));

const calls = { n: 0 };
const ctx = new Proxy({}, {
  get: (t, k) => (k in t ? t[k] : () => { calls.n += 1; }),
  set: (t, k, v) => { t[k] = v; return true; },
});
const canvas = { clientWidth: 1280, clientHeight: 720, width: 0, height: 0, getContext: () => ctx };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const until = async (cond, ms = 5000) => {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (cond()) return true; await sleep(20); }
  return false;
};

const content = await (await fetch(`http://${host}/api/content.json`)).json();
sim.configure(content.constants);
const net = new Net("NodeWeb", "", content.protocol_version);
await net.connect();
await until(() => (net.lobby.players || []).length === 1);
net.send("pick", { fighter: "ondina" });
net.send("add_bot");
await until(() => net.lobby.can_start);
net.send("start");
if (!(await until(() => net.gameGen === 1 && net.gameStart))) throw new Error("não começou");

let bits = 0;
const driver = new NetDriver(net, content, () => bits);
const r = new Renderer(canvas);
let events = 0;
const start = Date.now();
let ticks = 0;
while (Date.now() - start < 3000) {
  ticks += 1;
  bits = ticks % 120 < 60 ? sim.I.RIGHT : sim.I.LEFT;
  if (ticks % 45 === 0) bits |= sim.I.JUMP;
  events += driver.tick().length;
  r.resize();
  r.updateCamera(driver.world, 1 / 60);
  r.draw(driver.world, driver, new Map(), 0.5);
  await sleep(1000 / 60);
}
const me = driver.world.fighters.get(net.playerId);
console.log(JSON.stringify({ ticks, frame: driver.world.frame, pending: driver.pending.length,
  events, drawCalls: calls.n, meX: me.x, meState: me.state, fighter: me.fdef.key }));
net.close();
process.exit(0);
