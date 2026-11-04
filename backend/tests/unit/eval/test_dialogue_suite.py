import json
from unittest.mock import AsyncMock

import dialogue_suite
from dialogue_suite import append_evidence, manifest, read_evidence, write_inventory
from ledger import Attempt, RequestLedger


def test_manifest_is_repeatable_and_accounts_for_all_model_repetitions():
    first = manifest()
    assert first == manifest()
    assert first["trials"] == 60
    assert first["nominal_requests"] == 186
    assert first["request_ceiling"] == 210
    assert first["pipeline_dm_cap"] == 3


def test_v2_manifest_selects_models_cases_runs_and_checkpoint_without_mutating_defaults():
    first = manifest(
        models=["provider/model:free"], case_names=["npc_speaks"], runs=2, suite="offline"
    )
    assert first["suite"] == "offline"
    assert first["models"] == ["provider/model:free"]
    assert first["runs_per_model_case"] == 2
    assert first["trials"] == 2
    assert manifest()["suite"] == "adr-0017-final-v2"


def test_manifest_rejects_unknown_case_and_empty_selection():
    import pytest

    with pytest.raises(ValueError, match="unknown dialogue case"):
        manifest(case_names=["missing"])
    with pytest.raises(ValueError, match="at least one"):
        manifest(models=[])


def test_paid_manifest_requires_explicit_allowlist_and_preserves_the_allowlist_identity():
    import pytest

    with pytest.raises(ValueError, match="allowlist"):
        manifest(models=["vendor/paid"])
    plan = manifest(models=["vendor/paid"], paid_allowlist={"vendor/paid"})
    assert plan["models"] == ["vendor/paid"]
    assert plan["paid_allowlist"] == ["vendor/paid"]


async def test_dry_run_does_not_resolve_profiles_or_contact_catalog(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network or database access in dry-run")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    resolve = AsyncMock(side_effect=forbidden)
    catalog = AsyncMock(side_effect=forbidden)
    monkeypatch.setattr(dialogue_suite, "resolve_eval_generation", resolve)
    monkeypatch.setattr(dialogue_suite, "validate_eval_models", catalog)
    monkeypatch.setattr("sys.argv", ["dialogue_suite.py", "--dry-run"])
    await dialogue_suite.main()
    assert json.loads(capsys.readouterr().out)["trials"] == 60
    resolve.assert_not_called()
    catalog.assert_not_called()


async def test_paid_allowlist_dry_run_is_offline_and_not_live_authorization(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("Paid dry-run must remain offline")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    resolve = AsyncMock(side_effect=forbidden)
    catalog = AsyncMock(side_effect=forbidden)
    monkeypatch.setattr(dialogue_suite, "resolve_eval_generation", resolve)
    monkeypatch.setattr(dialogue_suite, "validate_eval_models", catalog)
    monkeypatch.setattr(
        "sys.argv",
        [
            "dialogue_suite.py",
            "--dry-run",
            "--models",
            "vendor/model",
            "--allow-paid-model",
            "vendor/model",
            "--cases",
            "npc_speaks",
            "--runs",
            "1",
        ],
    )
    await dialogue_suite.main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["models"] == ["vendor/model"]
    assert plan["paid_allowlist"] == ["vendor/model"]
    resolve.assert_not_called()
    catalog.assert_not_called()


def test_interrupted_trial_is_distinct_from_a_completed_trial(tmp_path):
    path = tmp_path / "trials.jsonl"
    append_evidence(path, {"event": "started", "key": "one"})
    rows, interrupted = read_evidence(path)
    assert rows == {} and interrupted == {"one"}
    append_evidence(path, {"event": "result", "key": "one", "requests": 2})
    rows, interrupted = read_evidence(path)
    assert rows["one"]["requests"] == 2 and not interrupted


def test_retry_attempt_supersedes_only_when_its_result_lands(tmp_path):
    path = tmp_path / "trials.jsonl"
    append_evidence(path, {"event": "started", "key": "one"})
    append_evidence(path, {"event": "result", "key": "one", "requests": 1, "retryable": True})
    append_evidence(path, {"event": "started", "key": "one"})
    rows, interrupted = read_evidence(path)
    assert rows["one"]["retryable"] and interrupted == {"one"}
    append_evidence(path, {"event": "result", "key": "one", "requests": 1, "retryable": False})
    rows, interrupted = read_evidence(path)
    assert not rows["one"]["retryable"] and not interrupted


def test_inventory_writes_usage_csv_and_markdown_from_ledger_rows(tmp_path):
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=2)
    attempt = Attempt(
        key="call-1",
        scenario="case-a",
        probe="case-a:dm",
        run=0,
        model="m:free",
        usage=[{"input_tokens": 4, "output_tokens": 3, "total_tokens": 7}],
    )
    ledger.reserve(attempt)
    attempt.status = "ok"
    ledger.record(attempt)
    earlier_path = tmp_path / "earlier-ledger.jsonl"
    earlier = RequestLedger(earlier_path, budget=1)
    earlier_attempt = Attempt(
        key="earlier-call",
        scenario="case-b",
        probe="case-b:actor",
        run=0,
        model="other:free",
        usage=[{"input_tokens": 2, "output_tokens": 1, "total_tokens": 3}],
    )
    earlier.reserve(earlier_attempt)
    earlier_attempt.status = "ok"
    earlier.record(earlier_attempt)
    plan = {
        "suite": "offline",
        "source_hash": "source",
        "trials": 0,
        "runs_per_model_case": 0,
        "cases": {},
        "models": [],
    }
    output = tmp_path / "results.jsonl"
    write_inventory(output, plan, {"trial": {"ledger": str(earlier_path)}}, ledger)
    assert "input_tokens" in output.with_suffix(".usage.csv").read_text()
    assert "| m:free | case-a |" in output.with_suffix(".usage.md").read_text()
    assert "| other:free | case-b |" in output.with_suffix(".usage.md").read_text()


def test_request_budget_stop_remains_incomplete_not_model_failure(tmp_path):
    plan = manifest(models=["m:free"], case_names=["npc_speaks"], runs=1)
    key = dialogue_suite.trial_key(plan, "npc_speaks", "m:free", 0)
    stopped = {
        "key": key,
        "case": "npc_speaks",
        "model": "m:free",
        "run": 0,
        "trial_status": "request_budget_stopped",
        "observed_checks": [],
    }
    output = tmp_path / "stopped.jsonl"
    write_inventory(output, plan, {key: stopped}, RequestLedger(tmp_path / "empty-ledger"))
    summary = json.loads(output.with_suffix(".summary.json").read_text())
    assert summary["all_trials_recorded"] is False
    assert summary["pending"] == [{"case": "npc_speaks", "model": "m:free", "run": 0}]
