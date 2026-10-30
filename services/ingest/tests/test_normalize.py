from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import h3
import pytest

from ingest.normalize import Envelope, InvalidBatch, normalize

BATCH = "0192f0c4-0000-7000-8000-000000000001"
STATE = ["4B1805", "SWR283  ", "Switzerland", 1793716288, 1793716289, 16.12, 48.02, 10363.2, False]
STATE += [231.4, 92.1, 0.0, None, 10500.0, "2331", False, 0, 4]
FLIGHT = {
    "icao24": "4B1805",
    "firstSeen": 1793577600,
    "lastSeen": 1793581800,
    "estDepartureAirport": "LSZH",
    "estArrivalAirport": None,
    "callsign": "SWR283  ",
    "estDepartureAirportHorizDistance": 1200,
    "estArrivalAirportHorizDistance": 900,
    "departureAirportCandidatesCount": 1,
    "arrivalAirportCandidatesCount": 2,
}


def states_env(states: Any, status: int = 200, time: Any = 1793716290) -> Envelope:
    response = {"time": time, "states": states} if status == 200 else None
    return Envelope.model_validate(
        {
            "batch_id": BATCH,
            "collector_id": "pc-daniel",
            "query": {"kind": "states_global", "extended": True},
            "requested_at": "2026-11-03T14:31:30.120Z",
            "http_status": status,
            "response": response,
        }
    )


def flights_env(response: Any) -> Envelope:
    return Envelope.model_validate(
        {
            "batch_id": BATCH,
            "collector_id": "pc-daniel",
            "query": {
                "kind": "flights_all",
                "begin": "2026-11-02T00:00:00Z",
                "end": "2026-11-02T02:00:00Z",
            },
            "requested_at": "2026-11-03T06:00:04.512Z",
            "http_status": 200,
            "response": response,
        }
    )


def test_state_row_is_normalised() -> None:
    result = normalize(states_env([STATE]))
    row = result.rows[0]
    assert result.snapshot_time == datetime.fromtimestamp(1793716290, UTC)
    assert (result.n_states, result.n_rejected) == (1, 0)
    assert row[1:4] == ("4b1805", "SWR283", "Switzerland")
    assert row[4] == datetime.fromtimestamp(1793716288, UTC)
    assert row[8:10] == (10363.2, 10500.0)  # baro, then geo from index 13
    assert row[14:18] == ("2331", False, 0, 4)
    assert row[18] == h3.str_to_int(h3.latlng_to_cell(48.02, 16.12, 4))
    assert row[19] == UUID(BATCH)


def test_empty_callsign_becomes_null() -> None:
    state = list(STATE)
    state[1] = "        "
    assert normalize(states_env([state])).rows[0][2] is None


def test_missing_position_has_no_h3_and_is_kept() -> None:
    state = list(STATE)
    state[5] = state[6] = None
    assert normalize(states_env([state])).rows[0][18] is None


@pytest.mark.parametrize(
    ("index", "value"),
    [
        (0, "zzzzzz"),
        (0, None),
        (6, 91.0),
        (6, -91.0),
        (5, 181.0),
        (5, -181.0),
        (3, "x"),
        (1, "a\x00"),
    ],
)
def test_bad_state_rows_are_counted_not_stored(index: int, value: Any) -> None:
    bad = list(STATE)
    bad[index] = value
    result = normalize(states_env([STATE, bad]))
    assert (len(result.rows), result.n_states, result.n_rejected) == (1, 2, 1)


def test_short_state_row_is_rejected_but_missing_category_is_fine() -> None:
    result = normalize(states_env([STATE[:10], STATE[:17]]))
    assert (len(result.rows), result.n_rejected) == (1, 1)
    assert result.rows[0][17] is None


def test_null_states_means_no_rows_but_a_snapshot() -> None:
    result = normalize(states_env(None))
    assert result.rows == []
    assert result.snapshot_time is not None


def test_failed_request_has_no_rows_or_snapshot() -> None:
    result = normalize(states_env(None, status=429))
    assert (result.rows, result.snapshot_time) == ([], None)


@pytest.mark.parametrize("time", [None, "soon", True])
def test_successful_states_batch_needs_a_time(time: Any) -> None:
    with pytest.raises(InvalidBatch):
        normalize(states_env([STATE], time=time))


def test_flight_row_is_normalised() -> None:
    result = normalize(flights_env([FLIGHT]))
    row = result.rows[0]
    assert result.snapshot_time is None
    assert row[0] == "4b1805"
    assert row[1] == datetime.fromtimestamp(1793577600, UTC)
    assert row[3:6] == ("SWR283", "LSZH", None)
    assert row[6:10] == (1200, 900, 1, 2)


@pytest.mark.parametrize("missing", ["icao24", "firstSeen", "lastSeen"])
def test_flight_rows_without_required_fields_are_rejected(missing: str) -> None:
    bad = {k: v for k, v in FLIGHT.items() if k != missing}
    result = normalize(flights_env([FLIGHT, bad]))
    assert (len(result.rows), result.n_states, result.n_rejected) == (1, 2, 1)


def test_flights_response_must_be_a_list() -> None:
    with pytest.raises(InvalidBatch):
        normalize(flights_env({"oops": 1}))
