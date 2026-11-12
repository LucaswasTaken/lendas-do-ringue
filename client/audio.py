"""Som do jogo: efeitos (com pan pela posição na tela) e música em loop.

Sem saída de áudio ou sem os .wav gerados, tudo vira silêncio sem quebrar o jogo.
Os sons vêm de `tools/build_audio.py`. M liga/desliga o som.
"""

from __future__ import annotations

import time

import arcade

from shared.paths import assets_dir

MIN_GAP = {"hit": 0.04, "swing": 0.04, "land": 0.08}
SFX_VOLUME = 0.6
MUSIC_VOLUME = 0.35

HEAVY_MOVES = ("heavy_", "recovery", "air_heavy_down")


class Audio:
    def __init__(self) -> None:
        self.sounds: dict[str, object | None] = {}
        self.last: dict[str, float] = {}
        self.muted = False
        self.enabled = True
        self.music_name: str | None = None
        self.music_player = None

    def _get(self, name: str):
        if name not in self.sounds:
            path = assets_dir() / "sounds" / f"{name}.wav"
            try:
                self.sounds[name] = arcade.load_sound(path) if path.is_file() else None
            except Exception:  # sem dispositivo de áudio
                self.sounds[name] = None
        return self.sounds[name]

    def play(self, name: str, volume: float = 1.0, pan: float = 0.0) -> None:
        if self.muted or not self.enabled:
            return
        now = time.perf_counter()
        if now - self.last.get(name, 0.0) < MIN_GAP.get(name, 0.0):
            return
        self.last[name] = now
        snd = self._get(name)
        if snd is None:
            return
        try:
            arcade.play_sound(snd, volume=volume * SFX_VOLUME, pan=max(-1.0, min(1.0, pan)))
        except Exception:
            self.enabled = False

    def on_event(self, ev: dict, pan: float) -> None:
        e = ev["e"]
        if e == "jump":
            self.play("airjump" if ev.get("air") else "jump", 0.6, pan)
        elif e == "attack":
            heavy = ev["m"].startswith(HEAVY_MOVES)
            self.play("swing_heavy" if heavy else "swing", 0.7, pan)
        elif e == "hit":
            self.play("hit_heavy" if ev["kb"] > 1100 else "hit", 1.0, pan)
        elif e == "ko":
            self.play("ko", 1.0, pan)
        elif e == "dodge":
            self.play("dodge", 0.6, pan)
        elif e == "ledge":
            self.play("ledge", 0.6, pan)
        elif e == "end":
            self.music(None)
            self.play("victory", 0.9)

    # ------------------------------------------------------------------ música
    def music(self, name: str | None) -> None:
        if name == self.music_name:
            return
        self.stop_music()
        self.music_name = name
        if name is None or self.muted or not self.enabled:
            return
        path = assets_dir() / "music" / f"{name}.wav"
        if not path.is_file():
            return
        try:
            snd = arcade.load_sound(path, streaming=True)
            self.music_player = arcade.play_sound(snd, volume=MUSIC_VOLUME, loop=True)
        except Exception:
            self.music_player = None

    def stop_music(self) -> None:
        if self.music_player is not None:
            try:
                arcade.stop_sound(self.music_player)
            except Exception:
                pass
        self.music_player = None
        self.music_name = None

    def toggle_mute(self) -> None:
        current = self.music_name
        self.muted = not self.muted
        if self.muted:
            self.stop_music()
            self.music_name = current  # lembra qual tocar ao desmutar
        else:
            self.music_name = None
            self.music(current)


audio = Audio()
