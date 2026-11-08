import json
import sys
import uuid
from unittest.mock import AsyncMock

import eval.dialogue.suite as dialogue_suite
import eval.smoke.model_smoke as model_smoke
import pytest
from eval.dialogue.execution import run_models
from eval.dialogue.plan import digest, manifest
from eval.dialogue.trial import run_case
from eval.support.ledger import Attempt, RequestLedger

from app.ai.router import ModelConfig
from tests.unit.eval.dialogue.test_dialogue_affinity import provider as provider


async def test_model_lanes_keep_distinct_sessions_through_budget_resume(provider, tmp_path):
    from eval.support.dialogue_affinity import session_id_for_model

    original, requests = provider
    models = ["vendor/a:free", "vendor/b:free"]
    plan = manifest(models=models, case_names=["npc_speaks", "actor_en"], runs=2)
    generations = {m: (original, ModelConfig("openrouter", m, 60000)) for m in models}
    ledger_path = tmp_path / "requests.jsonl"
    output = tmp_path / "trials.jsonl"
    completed = {}
    owner = uuid.uuid4()
    await run_models(
        plan,
        completed,
        RequestLedger(ledger_path, budget=3),
        output,
        generations,
        owner,
        "commit",
        run_case,
        {},
    )
    assert len(requests) == 3
    await run_models(
        plan,
        completed,
        RequestLedger(ledger_path, budget=8),
        output,
        generations,
        owner,
        "commit",
        run_case,
        {},
    )
    assert len(requests) == 8
    for request in requests:
        model = json.loads(request.content)["model"]
        assert request.headers["x-session-id"] == session_id_for_model(digest(plan), model)
    assert len({r.headers["x-session-id"] for r in requests}) == 2
    assert "x-session-id" not in original.client.default_headers


async def test_smoke_cli_shares_checkpoint_model_identity_across_all_trials(
    provider,
    tmp_path,
    monkeypatch,
):
    from eval.support.dialogue_affinity import session_id_for_model

    original, requests = provider

    async def resolve(owner, model):
        return original, ModelConfig("openrouter", model, 60000)

    monkeypatch.setattr(model_smoke, "resolve_eval_generation", resolve)
    monkeypatch.setattr(model_smoke, "validate_free_models", AsyncMock())
    monkeypatch.setattr(
        "sys.argv",
        [
            "smoke",
            "--model",
            "vendor/a:free",
            "--model",
            "vendor/b:free",
            "--probe",
            "npc_speaks",
            "--probe",
            "actor_language",
            "--scenario",
            "debug-thornhaven",
            "--runs",
            "2",
            "--checkpoint",
            "shared-checkpoint",
            "--user",
            str(uuid.uuid4()),
            "--ledger",
            str(tmp_path / "smoke.jsonl"),
            "--budget",
            "8",
        ],
    )
    await model_smoke.main()
    assert len(requests) == 8
    for request in requests:
        model = json.loads(request.content)["model"]
        assert request.headers["x-session-id"] == session_id_for_model("shared-checkpoint", model)
    monkeypatch.setattr("sys.argv", [*sys.argv, "--resume"])
    await model_smoke.main()
    assert len(requests) == 8


async def test_explicit_implicit_affinity_remains_available_offline(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["suite", "--dry-run", "--no-session-affinity"])
    await dialogue_suite.main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["execution"]["session_affinity"] == "implicit"


@pytest.mark.parametrize("headers", [{}, {"x-session-id": "old-trial-id"}])
async def test_smoke_refuses_changed_affinity_on_resume_before_network(
    tmp_path,
    monkeypatch,
    headers,
):
    path = tmp_path / "old-ledger.jsonl"
    ledger = RequestLedger(path, budget=8)
    previous = Attempt(
        key="old-completed",
        scenario="debug-thornhaven",
        probe="npc_speaks",
        run=0,
        checkpoint="shared-checkpoint",
        model="vendor/a:free",
        request_headers=headers,
    )
    ledger.reserve(previous)
    previous.status = "ok"
    ledger.record(previous)
    before = path.read_bytes()
    catalog = AsyncMock(side_effect=AssertionError("No catalog access"))
    profile = AsyncMock(side_effect=AssertionError("No credential resolution"))
    monkeypatch.setattr(model_smoke, "validate_free_models", catalog)
    monkeypatch.setattr(model_smoke, "resolve_eval_generation", profile)
    monkeypatch.setattr(
        "sys.argv",
        [
            "smoke",
            "--model",
            "vendor/a:free",
            "--probe",
            "npc_speaks",
            "--scenario",
            "debug-thornhaven",
            "--checkpoint",
            "shared-checkpoint",
            "--ledger",
            str(path),
            "--budget",
            "8",
            "--user",
            str(uuid.uuid4()),
            "--resume",
        ],
    )
    with pytest.raises(SystemExit) as error:
        await model_smoke.main()
    assert error.value.code == 2
    catalog.assert_not_awaited()
    profile.assert_not_awaited()
    assert path.read_bytes() == before
