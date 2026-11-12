"""A sim em JS (web/js/sim.js) precisa dar o mesmo resultado que a sim em Python.

Roda as duas com os mesmos inputs aleatórios e compara os snapshots. Pula se não houver Node.
"""

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from server.web import build_content
from tests.helpers import make_world

NODE = shutil.which("node")
RUNNER = Path(__file__).with_name("parity_runner.mjs")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js não instalado")

BUTTONS = [1, 2, 4, 8, 16, 32, 64, 128]


def _inputs(seed: int, frames: int, players: int) -> list[dict[int, int]]:
    rng = random.Random(seed)
    seq, cur = [], [0] * players
    for k in range(frames):
        if k % 5 == 0:
            cur = [sum(b for b in BUTTONS if rng.random() < 0.18) for _ in range(players)]
        seq.append(dict(enumerate(cur)))
    return seq


def _run_js(job: dict) -> list[dict]:
    out = subprocess.run([NODE, str(RUNNER)], input=json.dumps(job), capture_output=True,
                         text=True, encoding="utf-8", check=True, timeout=60)
    return json.loads(out.stdout)


def _close(a, b, path="") -> None:
    if isinstance(a, float) or isinstance(b, float):
        assert a == pytest.approx(b, rel=1e-9, abs=1e-6), path
    elif isinstance(a, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            _close(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _close(x, y, f"{path}[{i}]")
    else:
        assert a == b, path


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_full_sim_matches_python(seed):
    roster = ["ravena", "toro", "lince", "ondina"]
    seq = _inputs(seed, 1500, 4)
    content = json.loads(json.dumps(build_content(), default=list))
    js = _run_js({"content": content, "stage": "coliseu", "roster": roster,
                  "inputs": [{str(k): v for k, v in i.items()} for i in seq],
                  "every": 50, "mode": "full"})
    w = make_world(*roster)
    py = []
    for k, inp in enumerate(seq):
        w.step(inp)
        if (k + 1) % 50 == 0:
            s = w.snapshot()
            s.pop("events")
            py.append(json.loads(json.dumps(s)))
    assert len(js) == len(py)
    for i, (a, b) in enumerate(zip(py, js, strict=True)):
        _close(a, b, f"snap{i}")


def test_ledge_grab_and_climb_matches_python():
    # anda para fora do palco, volta segurando para o palco, agarra a borda e sobe (↑);
    # depois faz o mesmo pela esquerda e sai da borda com pulo. O roteiro reage ao estado
    # do Python; a mesma sequência de inputs vai para o JS.
    w = make_world("ravena", "toro")
    f = w.fighters[0]
    grabs, py, seq = 0, [], []
    phase, wait = 0, 0
    for _ in range(900):
        out, back = (2, 1) if phase < 2 else (1, 2)
        if f.state == "ledge":
            wait += 1
            bits = 0 if wait < 10 else (4 if phase == 0 else 16)
            if wait >= 10:
                phase, wait = phase + 1, 0
        elif phase in (0, 2) and f.grounded and abs(f.x) < 560:
            bits = out
        else:
            bits = back
        if phase == 1 and f.grounded:
            phase = 2
        inp = {0: bits}
        seq.append(inp)
        w.step(inp)
        grabs += sum(e["e"] == "ledge" for e in w.events)
        s = w.snapshot()
        s.pop("events")
        py.append(json.loads(json.dumps(s)))
    assert grabs >= 2  # o roteiro precisa mesmo passar pela borda
    content = json.loads(json.dumps(build_content(), default=list))
    js = _run_js({"content": content, "stage": "coliseu", "roster": ["ravena", "toro"],
                  "inputs": [{str(k): v for k, v in i.items()} for i in seq],
                  "every": 1, "mode": "full"})
    for i, (a, b) in enumerate(zip(py, js, strict=True)):
        _close(a, b, f"frame{i}")


def test_prediction_step_one_matches_python():
    seq = _inputs(9, 1200, 1)
    content = json.loads(json.dumps(build_content(), default=list))
    js = _run_js({"content": content, "stage": "planicie", "roster": ["lince", "toro"],
                  "inputs": [{"0": i[0]} for i in seq], "every": 20, "mode": "one"})
    w = make_world("lince", "toro", stage="planicie")
    py = []
    for k, inp in enumerate(seq):
        w.step_one(0, inp[0])
        if (k + 1) % 20 == 0:
            s = w.snapshot()
            s.pop("events")
            py.append(json.loads(json.dumps(s)))
    for i, (a, b) in enumerate(zip(py, js, strict=True)):
        _close(a, b, f"snap{i}")
