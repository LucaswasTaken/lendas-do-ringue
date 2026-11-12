"""Tela de partida: avança o driver (local ou online) a 60 Hz fixos e desenha com retângulos."""

from __future__ import annotations

import arcade

from client import rig
from client.audio import audio
from client.effects import Effects
from client.input import HELD
from shared import combat
from shared import constants as C
from shared.sim import Fighter

TAG_COLORS = [(255, 90, 90), (90, 160, 255), (120, 230, 120), (255, 210, 80)]


def damage_color(d: float) -> tuple[int, int, int]:
    t = min(1.0, d / 150)
    if t < 0.5:  # branco -> amarelo
        k = t / 0.5
        return 255, 255, int(255 * (1 - k))
    k = (t - 0.5) / 0.5  # amarelo -> vermelho escuro
    return 255 - int(80 * k), int(255 * (1 - k)), 0


class GameView(arcade.View):
    def __init__(self, driver) -> None:
        super().__init__()
        self.driver = driver
        self.world = driver.world
        self.acc = 0.0
        self.prev_pos = {f.pid: (f.x, f.y) for f in self.world.fighters.values()}
        self.paused = False
        self.show_boxes = False
        self.fx = Effects()
        self.colors = {f.pid: f.fdef.color for f in self.world.fighters.values()}
        self.camera = arcade.Camera2D()
        self.ui_camera = arcade.Camera2D()
        self.cam_x, self.cam_y, self.cam_zoom = 0.0, 150.0, 0.7
        self._texts: dict[str, arcade.Text] = {}

    # ------------------------------------------------------------------ util
    def text(self, key: str, value: str, x: float, y: float, size: int = 14,
             color=(255, 255, 255), anchor: str = "center", bold: bool = False) -> None:
        t = self._texts.get(key)
        if t is None:
            t = arcade.Text(value, x, y, color, size, anchor_x=anchor, bold=bold)
            self._texts[key] = t
        t.text, t.color, t.position = value, color, (x, y)
        t.draw()

    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        self.camera.match_window()
        self.ui_camera.match_window()

    # ------------------------------------------------------------------ input
    def on_key_press(self, key: int, modifiers: int) -> None:
        K = arcade.key
        online = self.driver.online
        if self.world.over and not online and key in (K.ENTER, K.RETURN, K.ESCAPE):
            self._back()
            return
        if key == K.ESCAPE:
            self.paused = not self.paused  # online o jogo não para: só mostra o menu
        elif key == K.Q and self.paused:
            self._back(leave=True)
        elif key == K.F1:
            self.show_boxes = not self.show_boxes
        elif key == K.M:
            audio.toggle_mute()
        HELD.add(key)

    def on_key_release(self, key: int, modifiers: int) -> None:
        HELD.discard(key)

    def on_show_view(self) -> None:
        audio.music("fight")

    def on_hide_view(self) -> None:
        HELD.clear()

    def _back(self, leave: bool = False) -> None:
        from client.menu_view import MenuView

        self.driver.close()
        if self.driver.online:
            from client.drivers import NetDriver
            from client.lobby_view import LobbyView

            net = self.driver.net
            if leave or not net.connected:
                net.close()
                self.window.show_view(MenuView(error=None if leave else "conexão perdida"))
            elif net.phase == "game" and net.game_gen != self.driver.gen:
                self.window.show_view(GameView(NetDriver(net)))  # voltou de uma reconexão
            else:
                self.window.show_view(LobbyView(net, gen=self.driver.gen))
            return
        self.window.show_view(MenuView())

    # ------------------------------------------------------------------ lógica
    def on_update(self, dt: float) -> None:
        self.fx.update(dt)
        if self.paused and not self.driver.online:
            return
        self.acc += min(dt, 0.25)
        while self.acc >= C.TICK_DT:
            self.acc -= C.TICK_DT
            self._tick()
        if self.driver.finished:
            self._back()
            return
        self._update_camera(dt)

    def _tick(self) -> None:
        w = self.world
        self.prev_pos = {f.pid: (f.x, f.y) for f in w.fighters.values()}
        for ev in self.driver.tick():
            self.fx.on_event(ev, self.colors)
            pan = (ev.get("x", self.cam_x) - self.cam_x) / 900
            audio.on_event(ev, pan)

    def _update_camera(self, dt: float) -> None:
        alive = [f for f in self.world.fighters.values() if f.alive]
        xs = [f.x for f in alive] + [0.0]
        ys = [f.y + 60 for f in alive] + [-60.0]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        span_w = max(xs) - min(xs) + 700
        span_h = max(ys) - min(ys) + 420
        hud = 120  # px da tela ocupados pelo HUD embaixo
        zoom = min(self.window.width / span_w, (self.window.height - hud) / span_h)
        zoom = max(0.35, min(1.15, zoom))
        cy -= hud / 2 / zoom  # desloca o mundo para cima do HUD
        k = min(1.0, dt * 5)
        self.cam_x += (cx - self.cam_x) * k
        self.cam_y += (cy - self.cam_y) * k
        self.cam_zoom += (zoom - self.cam_zoom) * k

    # ------------------------------------------------------------------ desenho
    def on_draw(self) -> None:
        self.clear(self.world.stage.background)
        ox, oy = self.fx.shake_offset()
        self.camera.position = (self.cam_x + ox, self.cam_y + oy)
        self.camera.zoom = self.cam_zoom
        with self.camera.activate():
            self._draw_stage()
            alpha = self.acc / C.TICK_DT
            for f in self.world.fighters.values():
                if f.alive:
                    self._draw_fighter(f, alpha)
            self.fx.draw()
        with self.ui_camera.activate():
            self._draw_hud()

    def _draw_stage(self) -> None:
        left, right, bottom, top = self.world.stage.blast
        arcade.draw_lrbt_rectangle_outline(left, right, bottom, top, (255, 255, 255, 25), 4)
        for p in self.world.stage.platforms:
            if p.soft:
                arcade.draw_lrbt_rectangle_filled(p.x, p.right, p.y, p.top, (150, 140, 190))
                arcade.draw_lrbt_rectangle_filled(p.x, p.right, p.top - 4, p.top, (210, 200, 250))
            else:
                arcade.draw_lrbt_rectangle_filled(p.x, p.right, p.y, p.top, (70, 64, 92))
                arcade.draw_lrbt_rectangle_filled(p.x, p.right, p.top - 14, p.top, (120, 170, 110))
                arcade.draw_lrbt_rectangle_filled(p.x, p.right, p.top - 18, p.top - 14,
                                                  (60, 100, 60))

    def _draw_fighter(self, f: Fighter, alpha: float) -> None:
        px, py = self.prev_pos.get(f.pid, (f.x, f.y))
        ox, oy = self.driver.offset(f.pid)
        x = px + (f.x - px) * alpha + ox
        y = py + (f.y - py) * alpha + oy
        w, h = f.fdef.width, f.fdef.height
        color = f.fdef.color
        a = 255
        if f.invuln > 0 and (self.world.frame // 4) % 2 == 0:
            a = 110
        if f.state == "hitstun":
            color = tuple(min(255, c + 90) for c in color)
        if f.state == "dodge":
            a = 120
        hh = h
        # sombra no chão
        if f.grounded:
            arcade.draw_ellipse_filled(x, y + 2, w * 1.3, 12, (0, 0, 0, 70))
        if f.charging:
            r = 10 + f.charge
            arcade.draw_circle_outline(x, y + hh / 2, w / 2 + r, (255, 220, 100, 170), 3)
        rig.draw(f, x, y, self.world.frame, a, color if f.state == "hitstun" else None)
        tag_color = TAG_COLORS[f.pid % 4]
        self.text(f"tag{f.pid}", self.driver.label(f.pid), x, y + hh + 14, 12, tag_color,
                  bold=True)
        arcade.draw_triangle_filled(x - 6, y + hh + 10, x + 6, y + hh + 10, x, y + hh + 3,
                                    tag_color)

        m = f.move
        if self.show_boxes and m and f.state == "attack" and not f.charging:
            af = f.move_frame - m.startup
            if 0 <= af < m.active:
                for hb in m.hitboxes:
                    if combat.hitbox_active(hb, af):
                        l_, r, b, t = combat.hitbox_rect(hb, x, y, f.facing)
                        arcade.draw_lrbt_rectangle_filled(l_, r, b, t, (255, 60, 60, 110))
                        arcade.draw_lrbt_rectangle_outline(l_, r, b, t, (255, 120, 120, 200), 2)
            elif af < 0:
                for hb in m.hitboxes:
                    l_, r, b, t = combat.hitbox_rect(hb, x, y, f.facing)
                    arcade.draw_lrbt_rectangle_outline(l_, r, b, t, (255, 200, 120, 70), 1)

    def _draw_hud(self) -> None:
        W, H = self.window.width, self.window.height
        secs = int(self.world.time_left)
        self.text("timer", f"{secs // 60}:{secs % 60:02d}", W / 2, H - 40, 22, bold=True)
        fs = list(self.world.fighters.values())
        slot_w = min(260, W / max(1, len(fs)))
        start = W / 2 - slot_w * len(fs) / 2
        for i, f in enumerate(fs):
            cx = start + slot_w * (i + 0.5)
            arcade.draw_lrbt_rectangle_filled(cx - slot_w / 2 + 8, cx + slot_w / 2 - 8, 14, 104,
                                              (10, 10, 18, 190))
            arcade.draw_lrbt_rectangle_filled(cx - slot_w / 2 + 8, cx + slot_w / 2 - 8, 100, 104,
                                              TAG_COLORS[f.pid % 4])
            tag = self.driver.label(f.pid)
            self.text(f"hn{f.pid}", f"{tag} · {f.fdef.name}", cx, 80, 12, (220, 220, 230))
            if f.state == "out":
                self.text(f"hd{f.pid}", "FORA", cx, 38, 26, (130, 130, 140), bold=True)
            else:
                self.text(f"hd{f.pid}", f"{int(f.damage)}%", cx, 36, 30,
                          damage_color(f.damage), bold=True)
            for s in range(f.stocks):
                sx = cx - (f.stocks - 1) * 9 + s * 18
                arcade.draw_circle_filled(sx, 24, 6, f.fdef.color)
        if self.driver.online and self.driver.net.reconnecting:
            arcade.draw_lrbt_rectangle_filled(0, W, H / 2 - 40, H / 2 + 40, (0, 0, 0, 170))
            self.text("recon", "Conexão caiu — reconectando...", W / 2, H / 2 - 8, 22,
                      (255, 200, 120), bold=True)
        if self.paused:
            online = self.driver.online
            arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (0, 0, 0, 150))
            self.text("pause", "MENU (o jogo continua)" if online else "PAUSA",
                      W / 2, H / 2 + 20, 40, bold=True)
            self.text("pause2", "Esc continua · Q " + ("sai da sala" if online else
                      "volta ao menu") + " · F1 mostra hitboxes",
                      W / 2, H / 2 - 30, 14, (200, 200, 210))
        if self.world.over:
            arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (0, 0, 0, 170))
            win = self.world.winner
            if win is None:
                msg = "EMPATE!"
            else:
                f = self.world.fighters[win]
                msg = f"{self.driver.label(win)} ({f.fdef.name}) VENCEU!"
            self.text("end", msg, W / 2, H / 2 + 80, 40, (255, 220, 120), bold=True)
            for i, f in enumerate(sorted(fs, key=lambda f: (-f.kos, f.falls))):
                self.text(f"res{i}", f"{self.driver.label(f.pid)} · {f.fdef.name}: "
                          f"{f.kos} KOs · {f.falls} quedas · {int(f.dealt)} de dano causado",
                          W / 2, H / 2 + 20 - i * 30, 16)
            hint = "voltando para a sala..." if self.driver.online else "Enter volta ao menu"
            self.text("end2", hint, W / 2, H / 2 - 120, 14, (200, 200, 210))
