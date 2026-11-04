import json
from unittest.mock import AsyncMock

import dialogue_suite
import pytest
from dialogue_plan import manifest, trial_key
from ledger import Attempt, RequestLedger

from app.ai.router import ModelConfig


async def test_explicit_resume_runs_a_trial_that_previously_stopped_before_any_request(
    monkeypatch,
    tmp_path,
):
    plan = manifest(models=["m:free"], case_names=["npc_speaks"], runs=1)
    key = trial_key(plan, "npc_speaks", "m:free", 0)
    output = tmp_path / "results.jsonl"
    dialogue_suite.append_evidence(
        output,
        {
            "event": "result",
            "key": key,
            "case": "npc_speaks",
            "model": "m:free",
            "run": 0,
            "trial_status": "request_budget_stopped",
            "requests": 0,
            "retryable": False,
        },
    )
    monkeypatch.setattr(dialogue_suite, "manifest", lambda *_: plan)
    monkeypatch.setattr(
        dialogue_suite.subprocess,
        "check_output",
        lambda args, **kw: "" if "status" in args else "commit",
    )
    monkeypatch.setattr(dialogue_suite, "validate_eval_models", AsyncMock())
    monkeypatch.setattr(
        dialogue_suite,
        "resolve_eval_generation",
        AsyncMock(return_value=(AsyncMock(), ModelConfig("openrouter", "m:free", 1000))),
    )
    run = AsyncMock(return_value=({}, []))
    monkeypatch.setattr(dialogue_suite, "run_case", run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "suite",
            "--resume",
            "--user",
            "00000000-0000-0000-0000-000000000001",
            "--budget",
            "1",
            "--ledger",
            str(tmp_path / "today.jsonl"),
            "--results",
            str(output),
        ],
    )
    await dialogue_suite.main()
    run.assert_awaited_once()
    assert json.loads(output.with_suffix(".summary.json").read_text())["all_trials_recorded"]


async def test_retry_with_the_same_ledger_is_rejected_before_catalog_or_profile_access(
    monkeypatch,
    tmp_path,
):
    plan = manifest(models=["m:free"], case_names=["npc_speaks"], runs=1)
    key = trial_key(plan, "npc_speaks", "m:free", 0)
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = RequestLedger(ledger_path, budget=2)
    attempt = Attempt(key=f"{key}|request-0", scenario="npc_speaks", probe="npc_speaks:dm", run=0)
    ledger.reserve(attempt)
    attempt.status = "error"
    ledger.record(attempt)
    output = tmp_path / "trials.jsonl"
    dialogue_suite.append_evidence(
        output,
        {
            "event": "result",
            "key": key,
            "requests": 1,
            "retryable": True,
            "ledger": str(ledger_path),
        },
    )
    monkeypatch.setattr(dialogue_suite, "manifest", lambda *_: plan)
    monkeypatch.setattr(
        dialogue_suite.subprocess,
        "check_output",
        lambda args, **kwargs: "" if "status" in args else "commit",
    )
    catalog = AsyncMock()
    profile = AsyncMock()
    monkeypatch.setattr(dialogue_suite, "validate_eval_models", catalog)
    monkeypatch.setattr(dialogue_suite, "resolve_eval_generation", profile)
    monkeypatch.setattr(
        "sys.argv",
        [
            "suite",
            "--resume",
            "--budget",
            "2",
            "--user",
            "00000000-0000-0000-0000-000000000001",
            "--ledger",
            str(ledger_path),
            "--results",
            str(output),
        ],
    )
    with pytest.raises(SystemExit):
        await dialogue_suite.main()
    catalog.assert_not_awaited()
    profile.assert_not_awaited()


def test_usage_inventory_keeps_superseded_attempts_with_same_request_key(tmp_path):
    paths = [tmp_path / "first.jsonl", tmp_path / "retry.jsonl"]
    output = tmp_path / "trials.jsonl"
    completed = {}
    for index, path in enumerate(paths):
        ledger = RequestLedger(path, budget=1)
        attempt = Attempt(
            key="same-trial|request-0",
            scenario="npc_speaks",
            probe="npc_speaks:dm",
            run=0,
            model="m:free",
        )
        ledger.reserve(attempt)
        attempt.status = "ok"
        attempt.usage = [{"input_tokens": index + 1}]
        ledger.record(attempt)
        row = {"event": "result", "key": "same-trial", "ledger": str(path)}
        dialogue_suite.append_evidence(output, row)
        completed["same-trial"] = row
    plan = {
        "suite": "offline",
        "source_hash": "source",
        "trials": 0,
        "runs_per_model_case": 0,
        "cases": {},
        "models": [],
    }
    dialogue_suite.write_inventory(output, plan, completed, RequestLedger(paths[-1]))
    csv = output.with_suffix(".usage.csv").read_text()
    assert csv.count("same-trial|request-0") == 2
