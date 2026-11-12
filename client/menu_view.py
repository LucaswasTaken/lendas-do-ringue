"""Tela inicial: partidas locais ou online (criar sala / entrar), tudo pelo teclado."""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass

import arcade

from client.audio import audio
from client.input import CONTROLS_HELP, HELD
from shared.constants import DEFAULT_PORT
from shared.content import fighters, stages

HOST_ROOM, JOIN_ROOM = -1, -2
MODES = [
    ("1P vs Bot", 1, 1),  # (rótulo, humanos, bots)
    ("2P local", 2, 0),
    ("1P vs 3 Bots", 1, 3),
    ("2P + 2 Bots", 2, 2),
    ("Bots se enfrentando", 0, 4),
    ("Online: criar sala", HOST_ROOM, 0),
    ("Online: entrar em sala", JOIN_ROOM, 0),
]
DIFFS = ["facil", "medio", "dificil"]
DIFF_LABEL = {"facil": "Fácil", "medio": "Médio", "dificil": "Difícil"}
ROW_MODE, ROW_NAME, ROW_P1, ROW_P2, ROW_DIFF, ROW_STAGE, ROW_GO = range(7)
TEXT_ROWS = (ROW_NAME,)


@dataclass
class MatchSetup:
    humans: int
    bots: int
    picks: list[str]  # lutador de cada jogador (humanos primeiro)
    difficulty: str
    stage: str


def start_local_server(host: str = "0.0.0.0", port: int = DEFAULT_PORT) -> None:
    """Sobe o servidor numa thread deste processo (para 'criar sala')."""
    import asyncio

    from server.game_server import GameServer

    ready = threading.Event()
    failed: list[BaseException] = []

    def run():
        async def main():
            ev = asyncio.Event()
            task = asyncio.create_task(GameServer().run(host, port, ev))
            await ev.wait()
            ready.set()
            await task

        try:
            asyncio.run(main())
        except BaseException as e:  # porta ocupada etc.
            failed.append(e)
            ready.set()

    threading.Thread(target=run, daemon=True).start()
    if not ready.wait(5) or failed:
        raise RuntimeError("não consegui abrir a sala (a porta "
                           f"{port} já está em uso?)")


def lan_ip() -> str:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class MenuView(arcade.View):
    _hosting = False  # o servidor da sala local já está de pé neste processo
    _name = f"Lutador{random.randint(100, 999)}"
    _address = ""

    def __init__(self, error: str | None = None) -> None:
        super().__init__()
        self.error = error
        self.fighter_keys = list(fighters())
        self.stage_keys = list(stages())
        self.mode = 0
        self.p1 = 0
        self.p2 = 1 % len(self.fighter_keys)
        self.diff = 1
        self.stage = 0
        self.row = 0
        self.typing_address = False
        self.title = arcade.Text("LENDAS DO RINGUE", 0, 0, (255, 220, 120), 46,
                                 anchor_x="center", bold=True)
        self.sub = arcade.Text("luta em plataforma entre amigos", 0, 0, (180, 180, 200), 14,
                               anchor_x="center")
        self.lines = [arcade.Text("", 0, 0, arcade.color.WHITE, 20, anchor_x="center")
                      for _ in range(7)]
        self.err_text = arcade.Text("", 0, 0, (240, 140, 140), 14, anchor_x="center")
        self.help = [arcade.Text(t, 0, 0, (170, 170, 190), 12, anchor_x="center")
                     for t in (*CONTROLS_HELP.values(),
                               "Menu: ↑↓ escolhe · ←→ altera · digite no campo de texto · "
                               "Enter começa · M som · Esc sai")]

    @property
    def humans(self) -> int:
        return MODES[self.mode][1]

    def _rows(self) -> list[tuple[str, str]]:
        label, humans, _ = MODES[self.mode]
        fs = fighters()
        online = humans < 0
        caret = "_" if (self.world_time_blink()) else " "
        rows = [("Modo", label)]
        rows.append(("Nome", (MenuView._name + (caret if self.row == ROW_NAME else ""))
                     if online else "—"))
        rows.append(("Lutador P1" if not online else "Lutador",
                     fs[self.fighter_keys[self.p1]].name if humans != 0 else "—"))
        rows.append(("Lutador P2", fs[self.fighter_keys[self.p2]].name if humans >= 2 else "—"))
        rows.append(("Bots", DIFF_LABEL[DIFFS[self.diff]] if not online else "— (na sala)"))
        if humans == JOIN_ROOM:
            addr = MenuView._address or ("" if self.row == ROW_STAGE else "127.0.0.1")
            rows.append(("Endereço", addr + (caret if self.row == ROW_STAGE else "")))
        elif humans == HOST_ROOM:
            rows.append(("Palco", "— (na sala)"))
        else:
            rows.append(("Palco", stages()[self.stage_keys[self.stage]].name))
        rows.append(("", "▶ ENTRAR" if online else "▶ LUTAR"))
        return rows

    def world_time_blink(self) -> bool:
        import time

        return int(time.time() * 2) % 2 == 0

    def _is_text_row(self) -> bool:
        return (self.humans < 0 and self.row == ROW_NAME) or \
            (self.humans == JOIN_ROOM and self.row == ROW_STAGE)

    def on_show_view(self) -> None:
        HELD.clear()
        audio.music("menu")

    def on_draw(self) -> None:
        self.clear((18, 18, 30))
        w, h = self.window.width, self.window.height
        self.title.position = (w / 2, h - 110)
        self.title.draw()
        self.sub.position = (w / 2, h - 145)
        self.sub.draw()
        for i, (name, value) in enumerate(self._rows()):
            t = self.lines[i]
            sel = i == self.row
            arrows = sel and name and not self._is_text_row()
            t.text = (f"{'◀ ' if arrows else ''}{name + ': ' if name else ''}{value}"
                      f"{' ▶' if arrows else ''}")
            t.color = (255, 230, 120) if sel else (220, 220, 230)
            t.position = (w / 2, h - 215 - i * 44)
            t.draw()
        if self.error:
            self.err_text.text = self.error
            self.err_text.position = (w / 2, 150)
            self.err_text.draw()
        for i, t in enumerate(self.help):
            t.position = (w / 2, 90 - i * 22)
            t.draw()

    def on_text(self, text: str) -> None:
        if not self._is_text_row():
            return
        text = "".join(c for c in text if c.isprintable())
        if self.row == ROW_NAME:
            MenuView._name = (MenuView._name + text)[:16]
        else:
            MenuView._address = (MenuView._address + text.strip())[:120]

    def on_key_press(self, key: int, modifiers: int) -> None:
        K = arcade.key
        typing = self._is_text_row()
        if key == K.BACKSPACE and typing:
            if self.row == ROW_NAME:
                MenuView._name = MenuView._name[:-1]
            else:
                MenuView._address = MenuView._address[:-1]
            return
        if key == K.V and modifiers & arcade.key.MOD_CTRL and typing:
            try:
                clip = self.window.get_clipboard_text() or ""
            except Exception:
                clip = ""
            if clip:
                self.on_text(clip)
            return
        if key == K.M and not typing:
            audio.toggle_mute()
            return
        if key in (K.UP, K.DOWN, K.LEFT, K.RIGHT):
            audio.play("click", 0.5)
        if key == K.UP or (key == K.W and not typing):
            self.row = (self.row - 1) % 7
        elif key == K.DOWN or (key == K.S and not typing):
            self.row = (self.row + 1) % 7
        elif key in (K.LEFT, K.RIGHT) or (key in (K.A, K.D) and not typing):
            self._change(-1 if key in (K.LEFT, K.A) else 1)
        elif key in (K.ENTER, K.RETURN, K.NUM_ENTER) or (key == K.SPACE and self.row == ROW_GO):
            self._start()
        elif key == K.ESCAPE:
            arcade.exit()

    def _change(self, d: int) -> None:
        n = len(self.fighter_keys)
        if self.row == ROW_MODE:
            self.mode = (self.mode + d) % len(MODES)
        elif self.row == ROW_P1:
            self.p1 = (self.p1 + d) % n
        elif self.row == ROW_P2:
            self.p2 = (self.p2 + d) % n
        elif self.row == ROW_DIFF:
            self.diff = (self.diff + d) % len(DIFFS)
        elif self.row == ROW_STAGE and self.humans >= 0:
            self.stage = (self.stage + d) % len(self.stage_keys)

    def _start(self) -> None:
        if self.humans < 0:
            self._start_online()
            return
        from client.drivers import LocalDriver
        from client.game_view import GameView

        _, humans, bots = MODES[self.mode]
        picks = [self.fighter_keys[self.p1], self.fighter_keys[self.p2]][:humans]
        used = set(picks)
        for k in self.fighter_keys:  # bots pegam lutadores diferentes quando possível
            if len(picks) >= humans + bots:
                break
            if k not in used:
                picks.append(k)
                used.add(k)
        while len(picks) < humans + bots:
            picks.append(self.fighter_keys[len(picks) % len(self.fighter_keys)])
        setup = MatchSetup(humans, bots, picks, DIFFS[self.diff], self.stage_keys[self.stage])
        self.window.show_view(GameView(LocalDriver(setup)))

    def _start_online(self) -> None:
        from client.lobby_view import LobbyView
        from client.net import NetClient
        from client.tunnel import normalize_server_url

        hint = ""
        try:
            if self.humans == HOST_ROOM:
                if not MenuView._hosting:
                    start_local_server()
                    MenuView._hosting = True
                url = f"ws://127.0.0.1:{DEFAULT_PORT}"
                hint = (f"Amigos na mesma rede entram com: {lan_ip()}   "
                        f"(pela internet: rode o servidor com --ngrok)")
            else:
                url = normalize_server_url(MenuView._address)
            net = NetClient(url, MenuView._name)
            net.connect()
        except Exception as e:  # noqa: BLE001 - mostra qualquer falha de conexão na tela
            self.error = f"Não conectou: {e}"
            return
        net.send_pick(self.fighter_keys[self.p1])
        self.window.show_view(LobbyView(net, hint))
