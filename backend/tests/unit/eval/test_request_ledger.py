from pathlib import Path

import pytest
from ledger import Attempt, BudgetExhaustedError, RequestLedger


def _attempt(key: str = "debug|travel_move|0") -> Attempt:
    scenario, probe, run = key.split("|")
    return Attempt(key=key, scenario=scenario, probe=probe, run=int(run))


def test_reserve_and_record_are_persisted(tmp_path: Path) -> None:
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=3)

    ledger.reserve(_attempt())
    ledger.record(Attempt(key="debug|travel_move|0", scenario="debug", probe="travel_move", run=0))

    assert ledger.spent == 1
    assert ledger.remaining == 2
    assert ledger.completed("debug|travel_move|0")

    reloaded = RequestLedger(tmp_path / "ledger.jsonl", budget=3)
    assert reloaded.spent == 1
    assert reloaded.completed("debug|travel_move|0")
    assert reloaded.interrupted() == []


def test_budget_refuses_the_call_that_would_overshoot(tmp_path: Path) -> None:
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=1)
    ledger.reserve(_attempt("a|p|0"))

    with pytest.raises(BudgetExhaustedError):
        ledger.reserve(_attempt("a|p|1"))

    assert ledger.spent == 1
    assert ledger.remaining == 0


def test_interrupted_reservation_counts_as_spent_and_can_be_retried(
    tmp_path: Path,
) -> None:
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=2)
    ledger.reserve(_attempt("a|p|0"))

    reloaded = RequestLedger(tmp_path / "ledger.jsonl", budget=2)
    assert reloaded.spent == 1
    assert reloaded.interrupted() == ["a|p|0"]
    assert not reloaded.completed("a|p|0")

    reloaded.reserve(_attempt("a|p|0"))
    assert reloaded.spent == 2
    assert reloaded.remaining == 0


def test_completed_attempt_is_never_reserved_twice(tmp_path: Path) -> None:
    ledger = RequestLedger(tmp_path / "ledger.jsonl")
    ledger.reserve(_attempt())
    ledger.record(_attempt())

    with pytest.raises(ValueError, match="already completed"):
        ledger.reserve(_attempt())


def test_error_attempt_still_costs_a_request(tmp_path: Path) -> None:
    ledger = RequestLedger(tmp_path / "ledger.jsonl")
    ledger.reserve(_attempt())
    ledger.record(
        Attempt(
            key="debug|travel_move|0",
            scenario="debug",
            probe="travel_move",
            run=0,
            status="error",
            error="rate limited",
        )
    )

    assert ledger.spent == 1
    assert ledger.completed("debug|travel_move|0")
