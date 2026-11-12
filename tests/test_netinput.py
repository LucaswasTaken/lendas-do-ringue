from shared import constants as C
from shared import inputs as I
from shared.netinput import InputQueue


def test_in_order_one_per_tick_and_repeat_when_empty():
    q = InputQueue()
    q.push([(1, I.LEFT), (2, I.RIGHT)])
    assert q.pop() == I.LEFT and q.ack == 1
    assert q.pop() == I.RIGHT and q.ack == 2
    assert q.pop() == I.RIGHT and q.ack == 2  # faltou input: repete, sem avançar o ack


def test_redundant_resend_is_ignored():
    q = InputQueue()
    q.push([(1, 1), (2, 2)])
    q.pop()
    q.pop()
    q.push([(1, 1), (2, 2), (3, 4)])
    assert q.pop() == 4 and q.ack == 3
    assert not q.pending


def test_starts_from_first_seen_seq_after_reconnect():
    q = InputQueue()
    q.push([(500, I.JUMP)])
    assert q.pop() == I.JUMP and q.ack == 500


def test_queue_too_long_drops_oldest_but_keeps_presses():
    q = InputQueue()
    entries = [(s, 0) for s in range(1, 20)]
    entries[0] = (1, I.JUMP)
    q.push(entries)
    bits = q.pop()
    assert bits & I.JUMP
    assert len(q.pending) <= C.MAX_INPUT_QUEUE
