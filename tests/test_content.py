from shared.content import MOVE_KEYS, fighters, stages


def test_all_fighters_load_with_full_moveset():
    fs = fighters()
    assert len(fs) >= 4
    for f in fs.values():
        assert set(MOVE_KEYS) <= set(f.moves)
        for m in f.moves.values():
            assert m.startup > 0 and m.active > 0 and m.recovery >= 0
            assert m.hitboxes, f"{f.key}.{m.key} sem hitbox"


def test_stages_have_spawns_inside_blast_zone():
    for s in stages().values():
        left, right, bottom, top = s.blast
        assert len(s.spawns) >= 4
        for x, y in s.spawns:
            assert left < x < right and bottom < y < top
