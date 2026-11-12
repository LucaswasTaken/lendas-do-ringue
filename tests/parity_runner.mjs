// Roda web/js/sim.js com uma sequência de inputs e imprime os snapshots (JSON) para o
// tests/test_web_parity.py comparar com o Python. Uso: node parity_runner.mjs < job.json
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const sim = await import(pathToFileURL(resolve(here, "../web/js/sim.js")).href);

const job = JSON.parse(readFileSync(0, "utf-8"));
const content = job.content;
sim.configure(content.constants);
const stage = content.stages[job.stage];
const roster = job.roster.map((k, i) => [i, content.fighters[k]]);
const world = new sim.World(stage, roster);
const out = [];
for (let i = 0; i < job.inputs.length; i++) {
  if (job.mode === "one") world.stepOne(0, job.inputs[i][0] || 0);
  else world.step(job.inputs[i]);
  if ((i + 1) % job.every === 0) {
    const s = world.snapshot();
    delete s.events;
    out.push(s);
  }
}
process.stdout.write(JSON.stringify(out));
