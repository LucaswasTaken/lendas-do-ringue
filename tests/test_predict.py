"""Predição + reconciliação com lag simulado, sem rede de verdade."""

import random
from collections import deque

from client.drivers import NetDriver
from shared import constants as C
from shared import inputs as I
from shared.content import fighters, stages
from shared.netinput import InputQueue
from shared.sim import World


class ScriptSource:
    def __init__(self) -> None:
        self.value = 0

    def bits(self) -> int:
        return self.value


class FakeNet:
    """Liga um NetDriver a uma sim de 'servidor' com atraso fixo nos dois sentidos."""

    def __init__(self, one_way_frames: int) -> None:
        self.delay = one_way_frames
        self.player_id = 0
        self.connected = True
        self.reconnecting = False
        self.phase = "game"
        self.game_gen = 1
        roster = [{"pid": 0, "fighter": "ravena", "name": "Eu", "bot": False},
                  {"pid": 1, "fighter": "toro", "name": "Outro", "bot": False}]
        self.game_start = {"stage": "coliseu", "stocks": 3, "seconds": 480, "roster": roster}
        self.server = World(stages()["coliseu"], [(0, fighters()["ravena"]),
                                                  (1, fighters()["toro"])])
        self.queue = InputQueue()
        self.snapshots: deque[dict] = deque()
        self.to_server: deque[tuple[int, list]] = deque()
        self.to_client: deque[tuple[int, dict]] = deque()
        self.now = 0
        self.other_bits = 0

    def send_inputs(self, entries) -> None:
        self.to_server.append((self.now + self.delay, list(entries)))

    def server_tick(self) -> None:
        self.now += 1
        while self.to_server and self.to_server[0][0] <= self.now:
            self.queue.push(self.to_server.popleft()[1])
        self.server.step({0: self.queue.pop(), 1: self.other_bits})
        if self.server.frame % C.SNAPSHOT_EVERY == 0:
            snap = self.server.snapshot()
            snap["ack"] = self.queue.ack
            self.to_client.append((self.now + self.delay, snap))
        while self.to_client and self.to_client[0][0] <= self.now:
            self.snapshots.append(self.to_client.popleft()[1])


def _play(lag_frames: int, seed: int, frames: int = 600):
    net = FakeNet(lag_frames)
    src = ScriptSource()
    drv = NetDriver(net, [src])
    rng = random.Random(seed)
    buttons = [I.LEFT, I.RIGHT, I.DOWN, I.JUMP, I.LIGHT, I.DODGE]
    for k in range(frames):
        if k % 6 == 0:
            src.value = sum(b for b in buttons if rng.random() < 0.25)
        net.server_tick()
        drv.tick()
    src.value = 0
    for _ in range(120):  # para de apertar e deixa tudo chegar
        net.server_tick()
        drv.tick()
    return net, drv


def test_prediction_converges_to_server_state():
    for lag in (0, 3, 8):
        net, drv = _play(lag, seed=lag)
        me, srv = drv.world.fighters[0], net.server.fighters[0]
        assert abs(me.x - srv.x) < 1e-6 and abs(me.y - srv.y) < 1e-6, lag
        assert me.state == srv.state


def test_local_input_moves_own_fighter_immediately_even_with_lag():
    net = FakeNet(one_way_frames=10)
    src = ScriptSource()
    drv = NetDriver(net, [src])
    for _ in range(90):  # cai e pousa
        net.server_tick()
        drv.tick()
    x0 = drv.world.fighters[0].x
    src.value = I.RIGHT
    net.server_tick()
    drv.tick()
    drv.tick()
    assert drv.world.fighters[0].x > x0  # sem esperar os 20 frames de ida e volta


def test_other_fighter_is_interpolated_behind_server():
    net = FakeNet(one_way_frames=2)
    drv = NetDriver(net, [ScriptSource()])
    net.other_bits = I.LEFT
    for _ in range(200):
        net.server_tick()
        drv.tick()
    shown, real = drv.world.fighters[1].x, net.server.fighters[1].x
    assert shown > real  # anda para a esquerda; o desenhado está um pouco no passado
    assert shown - real < 200
