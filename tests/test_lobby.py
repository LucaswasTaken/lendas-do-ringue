from server.lobby import Lobby


def make():
    return Lobby(["ravena", "toro", "lince", "ondina"], ["coliseu", "planicie"])


def test_first_human_is_host_and_host_passes_on_leave():
    lb = make()
    a = lb.join("Ana", "t1")
    b = lb.join("Bia", "t2")
    assert lb.host_id == a.id
    lb.leave(a.id)
    assert lb.host_id == b.id


def test_only_host_controls_room_and_start_needs_ready():
    lb = make()
    a = lb.join("Ana", "t1")
    b = lb.join("Bia", "t2")
    assert not lb.set_stage(b.id, "planicie")
    assert lb.set_stage(a.id, "planicie") and lb.stage == "planicie"
    assert not lb.can_start(a.id)
    lb.set_ready(b.id, True)
    assert lb.can_start(a.id) and not lb.can_start(b.id)


def test_bots_fill_slots_until_full_and_room_empties_without_humans():
    lb = make()
    a = lb.join("Ana", "t1")
    assert lb.add_bot(a.id) and lb.add_bot(a.id) and lb.add_bot(a.id)
    assert lb.add_bot(a.id) is None
    assert lb.join("Late", "t9") is None
    assert lb.can_start(a.id)
    lb.leave(a.id)
    assert not lb.players


def test_reconnect_by_token():
    lb = make()
    a = lb.join("Ana", "tok")
    assert lb.by_token("tok") is a and lb.by_token("") is None
