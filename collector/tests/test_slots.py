from collector.slots import next_slot


def test_next_slot_rounds_up_to_the_grid() -> None:
    assert next_slot(1000.0, cadence=90, offset=0) == 1080


def test_next_slot_applies_the_offset() -> None:
    assert next_slot(1000.0, cadence=90, offset=45) == 1035


def test_now_exactly_on_a_slot_is_that_slot() -> None:
    assert next_slot(1080.0, cadence=90, offset=0) == 1080
