import math


def next_slot(now: float, cadence: int, offset: int) -> float:
    """First slot at or after `now` (unix s) on this collector's grid, docs/04 P1 step 1."""
    return math.ceil((now - offset) / cadence) * cadence + offset
