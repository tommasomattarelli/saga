from ledger import Attempt, RequestLedger
from model_smoke import report


def _record(ledger, scenario, digest, *, commit="abc", run=0):
    row = Attempt(
        f"pr1|model|{scenario}|travel_move|{run}|{commit}|{digest}",
        scenario,
        "travel_move",
        run,
        checkpoint="pr1",
        model="model",
        commit=commit,
    )
    ledger.reserve(row)
    row.status = "ok"
    ledger.record(row)


def test_report_separates_changed_requests_and_commits(tmp_path, capsys):
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=4)
    _record(ledger, "empty", "first")
    _record(ledger, "empty", "changed")
    _record(ledger, "empty", "first", commit="def")
    _record(ledger, "bloat", "larger")
    report(ledger, "pr1", ["model"], None)
    output = capsys.readouterr().out
    assert output.count("1/1; provider errors=0") == 4
    assert "Δ" not in output


def test_report_retains_scenario_delta_for_unambiguous_same_commit_samples(tmp_path, capsys):
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=2)
    _record(ledger, "empty", "first")
    _record(ledger, "bloat", "larger")
    report(ledger, "pr1", ["model"], None)
    assert "Δ model/travel_move: bloat vs empty +0%" in capsys.readouterr().out
