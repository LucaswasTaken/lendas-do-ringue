"""Sala online: escolher lutador, ficar pronto; o anfitrião escolhe palco, bots e inicia."""

from __future__ import annotations

import arcade

from client.audio import audio
from client.input import HELD
from server.lobby import BOT_LEVELS
from shared.content import fighters, stages

LEVEL_LABEL = {"facil": "Fácil", "medio": "Médio", "dificil": "Difícil"}


class LobbyView(arcade.View):
    def __init__(self, net, address_hint: str = "", gen: int | None = None) -> None:
        super().__init__()
        self.net = net
        self.address_hint = address_hint
        # partida que já foi mostrada; uma geração diferente com fase "game" abre o jogo
        self.gen = net.game_gen if gen is None else gen
        self.fighter_keys = list(fighters())
        self.stage_keys = list(stages())
        self._texts: dict[str, arcade.Text] = {}

    def text(self, key: str, value: str, x: float, y: float, size: int = 14,
             color=(230, 230, 240), anchor: str = "center", bold: bool = False) -> None:
        t = self._texts.get(key)
        if t is None:
            t = arcade.Text(value, x, y, color, size, anchor_x=anchor, bold=bold)
            self._texts[key] = t
        t.text, t.color, t.position = value, color, (x, y)
        t.draw()

    def on_show_view(self) -> None:
        HELD.clear()
        audio.music("menu")

    def on_update(self, dt: float) -> None:
        net = self.net
        if not net.connected and not net.reconnecting:
            from client.menu_view import MenuView

            self.window.show_view(MenuView(error=net.error or "conexão com o servidor perdida"))
            return
        if net.game_gen != self.gen and net.phase == "game" and net.game_start:
            from client.drivers import NetDriver
            from client.game_view import GameView

            self.window.show_view(GameView(NetDriver(net)))

    def on_key_press(self, key: int, modifiers: int) -> None:
        K = arcade.key
        net = self.net
        me = net.me()
        lb = net.lobby
        if key == K.ESCAPE:
            from client.menu_view import MenuView

            net.close()
            self.window.show_view(MenuView())
            return
        if me is None:
            return
        if key in (K.LEFT, K.RIGHT, K.A, K.D):
            d = -1 if key in (K.LEFT, K.A) else 1
            i = self.fighter_keys.index(me["fighter"]) if me["fighter"] in self.fighter_keys else 0
            net.send_pick(self.fighter_keys[(i + d) % len(self.fighter_keys)])
        elif key in (K.SPACE, K.R) and not net.is_host():
            net.send_ready(not me["ready"])
        elif not net.is_host():
            return
        elif key == K.P:
            i = self.stage_keys.index(lb.get("stage", self.stage_keys[0]))
            net.send_stage(self.stage_keys[(i + 1) % len(self.stage_keys)])
        elif key == K.N:
            i = BOT_LEVELS.index(lb.get("bot_level", "medio"))
            net.send_bot_level(BOT_LEVELS[(i + 1) % len(BOT_LEVELS)])
        elif key == K.B:
            net.send_add_bot()
        elif key == K.X:
            net.send_remove_bot()
        elif key in (K.ENTER, K.RETURN, K.NUM_ENTER):
            net.send_start()

    def on_draw(self) -> None:
        self.clear((18, 18, 30))
        W, H = self.window.width, self.window.height
        net, lb = self.net, self.net.lobby
        self.text("title", "SALA ONLINE", W / 2, H - 80, 34, (255, 220, 120), bold=True)
        if self.address_hint:
            self.text("addr", self.address_hint, W / 2, H - 115, 13, (170, 200, 170))
        st = stages().get(lb.get("stage", ""), None)
        info = (f"Palco: {st.name if st else '?'}   ·   "
                f"Bots: {LEVEL_LABEL.get(lb.get('bot_level', 'medio'), '?')}")
        self.text("info", info, W / 2, H - 150, 16)
        fs = fighters()
        for i, pl in enumerate(lb.get("players", [])):
            y = H - 220 - i * 54
            host = " (anfitrião)" if pl["id"] == lb.get("host") else ""
            you = "  ← você" if pl["id"] == net.player_id else ""
            status = "BOT" if pl["bot"] else ("PRONTO" if pl["ready"] or host else "esperando")
            col = (255, 230, 120) if pl["id"] == net.player_id else (230, 230, 240)
            fd = fs.get(pl["fighter"])
            if fd:
                arcade.draw_lrbt_rectangle_filled(W / 2 - 330, W / 2 - 306, y - 4, y + 22,
                                                  fd.color)
            self.text(f"pl{i}", f"{pl['name']}{host} · {fd.name if fd else pl['fighter']}"
                      f"  [{status}]{you}", W / 2 - 290, y, 18, col, anchor="left")
        for i in range(len(lb.get("players", [])), 4):
            self.text(f"pl{i}", "— vaga livre —", W / 2 - 290, H - 220 - i * 54, 16,
                      (110, 110, 130), anchor="left")
        if net.is_host():
            hint = ("←→ lutador · P palco · N dificuldade · B põe bot · X tira bot · "
                    "Enter inicia · Esc sai")
            ready = "Pode iniciar!" if lb.get("can_start") else \
                "Precisa de 2+ lutadores e todos prontos"
            self.text("ready", ready, W / 2, 120, 16,
                      (140, 230, 140) if lb.get("can_start") else (220, 170, 120))
        else:
            hint = "←→ lutador · Espaço pronto · Esc sai   (o anfitrião inicia)"
        self.text("hint", hint, W / 2, 80, 13, (170, 170, 190))
        if lb.get("notice"):
            self.text("notice", lb["notice"], W / 2, 150, 14, (230, 160, 160))
