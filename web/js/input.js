// Teclado + controle (Gamepad API) -> bitmask de shared/inputs.py.
import { I } from "./sim.js";

const held = new Set();
const KEYS = {
  KeyA: I.LEFT, ArrowLeft: I.LEFT, KeyD: I.RIGHT, ArrowRight: I.RIGHT,
  KeyW: I.UP, ArrowUp: I.UP, KeyS: I.DOWN, ArrowDown: I.DOWN,
  Space: I.JUMP, KeyJ: I.LIGHT, KeyZ: I.LIGHT, KeyK: I.HEAVY, KeyX: I.HEAVY,
  KeyL: I.DODGE, KeyC: I.DODGE, ShiftLeft: I.DODGE,
};
const DEAD = 0.45;

export function installInput() {
  window.addEventListener("keydown", (e) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
    if (KEYS[e.code] !== undefined) e.preventDefault();
    held.add(e.code);
  });
  window.addEventListener("keyup", (e) => held.delete(e.code));
  window.addEventListener("blur", () => held.clear());
}

function gamepadBits() {
  let out = 0;
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  for (const g of pads) {
    if (!g) continue;
    const b = (i) => g.buttons[i] && g.buttons[i].pressed;
    const ax = g.axes[0] || 0, ay = g.axes[1] || 0; // y para baixo = positivo
    if (ax < -DEAD || b(14)) out |= I.LEFT;
    if (ax > DEAD || b(15)) out |= I.RIGHT;
    if (ay < -DEAD || b(12)) out |= I.UP;
    if (ay > DEAD || b(13)) out |= I.DOWN;
    if (b(0)) out |= I.JUMP;
    if (b(2)) out |= I.LIGHT;
    if (b(1) || b(3)) out |= I.HEAVY;
    if (b(4) || b(5) || b(6) || b(7)) out |= I.DODGE;
    break; // só o primeiro controle
  }
  return out;
}

export function readBits() {
  let out = 0;
  for (const code of held) if (KEYS[code] !== undefined) out |= KEYS[code];
  return out | gamepadBits();
}

export function clearHeld() { held.clear(); }
