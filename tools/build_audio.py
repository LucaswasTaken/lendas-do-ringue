"""Gera os efeitos sonoros e as músicas por síntese (originais, sem licença externa).

Uso: uv run python tools/build_audio.py
Saída: assets/sounds/*.wav e assets/music/*.wav (mono, 16 bits, 22 050 Hz)
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SR = 22050
RNG = np.random.default_rng(42)


# --------------------------------------------------------------------------- blocos básicos
def t_axis(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def env(n: int, a=0.005, d=0.1, s=0.0, r=0.05, hold=0.0) -> np.ndarray:
    """Envelope ADSR com `n` amostras (s = nível de sustentação)."""
    a_n, d_n, r_n, h_n = (int(x * SR) for x in (a, d, r, hold))
    e = np.concatenate([np.linspace(0, 1, max(a_n, 1)),
                        np.linspace(1, s, max(d_n, 1)),
                        np.full(max(h_n, 0), s),
                        np.linspace(s, 0, max(r_n, 1))])
    if len(e) < n:
        e = np.concatenate([e, np.zeros(n - len(e))])
    return e[:n]


def osc(freq, dur, kind="sine") -> np.ndarray:
    t = t_axis(dur)
    if np.ndim(freq):
        ph = 2 * np.pi * np.cumsum(np.broadcast_to(np.asarray(freq, float), t.shape)) / SR
    else:
        ph = 2 * np.pi * freq * t
    if kind == "sine":
        return np.sin(ph)
    if kind == "square":
        return np.sign(np.sin(ph)) * 0.6
    if kind == "saw":
        return 2 * ((ph / (2 * np.pi)) % 1) - 1
    if kind == "tri":
        return 2 * np.abs(2 * ((ph / (2 * np.pi)) % 1) - 1) - 1
    raise ValueError(kind)


def sweep(f0, f1, dur, kind="sine", curve=2.0) -> np.ndarray:
    k = np.linspace(0, 1, int(dur * SR)) ** curve
    return osc(f0 + (f1 - f0) * k, dur, kind)


def noise(dur) -> np.ndarray:
    return RNG.uniform(-1, 1, int(dur * SR))


def lowpass(x: np.ndarray, cutoff) -> np.ndarray:
    """Filtro passa-baixa de 1 polo; `cutoff` pode variar no tempo."""
    c = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    alpha = 1 - np.exp(-2 * np.pi * c / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += alpha[i] * (x[i] - acc)
        y[i] = acc
    return y


def highpass(x, cutoff):
    return x - lowpass(x, cutoff)


def pad_to(x, n):
    return np.concatenate([x, np.zeros(max(0, n - len(x)))])[:n]


def mix(*parts):
    n = max(len(p) for p in parts)
    return sum(pad_to(p, n) for p in parts)


def norm(x, peak=0.9):
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


def note(n: str) -> float:
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8,
             "A": 9, "A#": 10, "B": 11}
    name, octave = n[:-1], int(n[-1])
    return 440.0 * 2 ** ((names[name] + 12 * (octave - 4) - 9) / 12)


def save(path: Path, x: np.ndarray, peak=0.9):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (norm(x, peak) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def n_(d: float) -> int:
    return int(d * SR)


# --------------------------------------------------------------------------- efeitos
def sfx() -> dict[str, np.ndarray]:
    s = {}
    d = 0.16
    s["jump"] = sweep(260, 620, d, "tri", 0.7) * env(n_(d), 0.003, 0.14) * 0.6
    d = 0.2
    s["airjump"] = mix(sweep(380, 900, d, "tri", 0.6) * env(n_(d), 0.003, 0.18) * 0.5,
                       highpass(noise(d), 2500) * env(n_(d), 0.002, 0.12) * 0.25)
    d = 0.14
    s["swing"] = (highpass(noise(d), 1400) * env(n_(d), 0.004, 0.12)
                  * (0.4 + 0.6 * sweep(0.2, 1, d, "sine")))
    d = 0.3
    s["swing_heavy"] = mix(highpass(noise(d), 700) * env(n_(d), 0.02, 0.26) * 0.8,
                           sweep(120, 70, d) * env(n_(d), 0.01, 0.25) * 0.4)
    d = 0.12
    s["hit"] = mix(lowpass(noise(d), 2200) * env(n_(d), 0.001, 0.09),
                   sweep(220, 90, d) * env(n_(d), 0.001, 0.1) * 0.7)
    d = 0.35
    s["hit_heavy"] = mix(lowpass(noise(d), np.linspace(5000, 400, n_(d))) * env(n_(d), 0.001,
                                                                                0.3),
                         sweep(140, 40, d) * env(n_(d), 0.001, 0.3) * 1.0,
                         highpass(noise(0.05), 3000) * 0.6)
    d = 1.1
    s["ko"] = mix(lowpass(noise(d), np.linspace(6000, 150, n_(d))) * env(n_(d), 0.002, 1.0),
                  sweep(110, 28, d) * env(n_(d), 0.002, 0.9) * 1.0,
                  sweep(1800, 300, 0.5, "square") * env(n_(0.5), 0.001, 0.45) * 0.25)
    d = 0.22
    s["dodge"] = highpass(noise(d), 3000) * env(n_(d), 0.03, 0.18) * \
        (0.3 + 0.7 * sweep(1, 0.2, d)) * 0.5
    d = 0.1
    s["land"] = lowpass(noise(d), 600) * env(n_(d), 0.001, 0.08) * 0.6
    d = 0.06
    s["click"] = highpass(noise(d), 2000) * env(n_(d), 0.001, 0.05) * 0.5
    d = 0.5
    s["ledge"] = mix(osc(note("E5"), 0.08, "square") * 0.3,
                     lowpass(noise(d), 900) * env(n_(d), 0.001, 0.12) * 0.4)
    s["victory"] = fanfare(["G4", "C5", "E5", "G5", "C6"])
    return s


def fanfare(seq):
    parts = []
    for i, n in enumerate(seq):
        dur = 0.16 if i < len(seq) - 1 else 1.4
        tone = osc(note(n), dur, "saw") * 0.5 + osc(note(n) * 2, dur, "square") * 0.15
        parts.append(lowpass(tone, 3000) * env(n_(dur), 0.01, dur * 0.6, 0.4, dur * 0.3))
    return np.concatenate(parts)


# --------------------------------------------------------------------------- música
CHORDS = {
    "Em": ["E3", "G3", "B3"], "C": ["C3", "E3", "G3"], "D": ["D3", "F#3", "A3"],
    "B": ["B2", "D#3", "F#3"], "Am": ["A2", "C3", "E3"], "G": ["G2", "B2", "D3"],
}


def place(track, x, start):
    i = int(start * SR)
    end = min(len(track), i + len(x))
    track[i:end] += x[:end - i]


def loopify(track: np.ndarray, total: float) -> np.ndarray:
    """Dobra a cauda sobre o começo para a música repetir sem emenda."""
    n = int(total * SR)
    tail = track[n:]
    out = track[:n].copy()
    out[:len(tail)] += tail
    return out


def music_fight() -> np.ndarray:
    bpm, beats = 138, 4
    prog = ["Em", "C", "D", "B"] * 4
    beat = 60 / bpm
    bar = beat * beats
    total = bar * len(prog)
    track = np.zeros(int(total * SR) + SR * 2)
    kick = sweep(160, 45, 0.22) * env(n_(0.22), 0.001, 0.2)
    snare = mix(highpass(noise(0.16), 1600) * env(n_(0.16), 0.001, 0.14) * 0.7,
                osc(200, 0.1, "tri") * env(n_(0.1), 0.001, 0.09) * 0.4)
    hat = highpass(noise(0.04), 6500) * env(n_(0.04), 0.001, 0.035) * 0.3
    rng = np.random.default_rng(11)
    scale = ["E5", "G5", "A5", "B5", "D6", "E6"]
    motif = [scale[i] for i in rng.integers(0, len(scale), 8)]
    for b, ch in enumerate(prog):
        t0 = b * bar
        freqs = [note(n) for n in CHORDS[ch]]
        for k in range(beats):
            place(track, kick, t0 + k * beat)
            if k % 2 == 1:
                place(track, snare, t0 + k * beat)
        for k in range(beats * 2):
            place(track, hat, t0 + k * beat / 2)
            f = freqs[0] * (2 if k % 2 else 1)
            tone = lowpass(osc(f, beat / 2, "saw"), 700) * env(n_(beat / 2), 0.003, beat * 0.4)
            place(track, tone * 0.3, t0 + k * beat / 2)
        stab = sum(osc(f * 2, beat * 0.4, "square") for f in freqs)
        for k in (0, 1.5, 3):
            place(track, lowpass(stab, 2400) * env(n_(beat * 0.4), 0.003, beat * 0.35) * 0.07,
                  t0 + k * beat)
        if b >= 8:  # melodia na segunda metade
            for k, n in enumerate(motif):
                if (k + b) % 4 == 3:
                    continue
                f = note(n)
                tone = osc(f, beat / 2, "tri") + osc(f * 2.004, beat / 2, "square") * 0.2
                place(track, tone * env(n_(beat / 2), 0.004, beat * 0.4) * 0.15,
                      t0 + k * beat / 2)
    return loopify(track, total)


def music_menu() -> np.ndarray:
    bpm, beats = 96, 4
    prog = ["Am", "G", "C", "Em"] * 2
    bar = 60 / bpm * beats
    total = bar * len(prog)
    track = np.zeros(int(total * SR) + SR * 3)
    for b, ch in enumerate(prog):
        t0 = b * bar
        freqs = [note(n) * 2 for n in CHORDS[ch]]
        pad = sum(osc(f * (1 + det), bar + 0.5, "saw") for f in freqs for det in (-0.004, 0.004))
        place(track, lowpass(pad, 1000) * env(n_(bar + 0.5), 0.4, 0.4, 0.7, 0.6) * 0.1, t0)
        for k in range(8):
            f = freqs[k % 3] * 2
            place(track, osc(f, 0.3, "tri") * env(n_(0.3), 0.002, 0.28) * 0.12,
                  t0 + k * bar / 8)
        place(track, osc(freqs[0] / 4, bar, "tri") * env(n_(bar), 0.05, bar, 0.6, 0.2) * 0.2, t0)
    return loopify(track, total)


def main() -> None:
    out = ROOT / "assets" / "sounds"
    for name, x in sfx().items():
        save(out / f"{name}.wav", x)
    music = ROOT / "assets" / "music"
    save(music / "fight.wav", music_fight(), 0.75)
    save(music / "menu.wav", music_menu(), 0.75)
    print("áudio gerado em", out, "e", music)


if __name__ == "__main__":
    main()
