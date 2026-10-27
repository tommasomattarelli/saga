import uuid
from unittest.mock import AsyncMock

import pytest
import scenario
from ledger import RequestLedger


async def test_eval_resolves_personal_configuration_without_mutating_it(monkeypatch):
    from live_calls import resolve_eval_generation

    from app.ai.router import ModelConfig

    config = ModelConfig("openrouter", "personal-model", 60000)
    provider = AsyncMock()
    resolved = AsyncMock(return_value=(provider, config))
    monkeypatch.setattr("live_calls.get_user_generation", resolved)
    result = await resolve_eval_generation(
        uuid.UUID(int=1), "nvidia/nemotron-3-ultra-550b-a55b:free"
    )
    resolved.assert_awaited_once_with(uuid.UUID(int=1))
    assert result[1].model.endswith(":free")
    assert result[1].max_tokens == 60000
    assert config.model == "personal-model"


async def test_resume_is_bound_to_checkpoint_model_and_exact_request(monkeypatch, tmp_path):
    from live_calls import run_trial

    from app.ai.providers.schemas import AgentResponse
    from app.ai.router import ModelConfig

    provider = AsyncMock()
    provider.generate_with_tools.return_value = AgentResponse(text="You set out.")
    generation = (provider, ModelConfig("openrouter", "model:free", 60000))
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=3)
    sc = scenario.load("debug-shrine")
    first = await run_trial(generation, sc, "travel_move", 0, ledger, checkpoint="baseline")
    assert first is not None and first.request and first.response
    assert first.checkpoint == "baseline"
    assert await run_trial(generation, sc, "travel_move", 0, ledger, checkpoint="baseline") is None
    await run_trial(generation, sc, "travel_move", 0, ledger, checkpoint="pr1")
    sc.stimuli["travel_move"].player += " I take a different approach."
    await run_trial(generation, sc, "travel_move", 0, ledger, checkpoint="pr1")
    assert ledger.spent == 3
    assert provider.generate_with_tools.await_count == 3


async def test_rate_limit_is_recorded_and_pauses_without_retry(monkeypatch, tmp_path):
    import httpx
    import openai
    from live_calls import EvaluationPausedError, run_trial

    from app.ai.router import ModelConfig

    provider = AsyncMock()
    provider.generate_with_tools.side_effect = openai.RateLimitError(
        "Limited",
        response=httpx.Response(429, request=httpx.Request("POST", "https://test")),
        body={},
    )
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=3)
    with pytest.raises(EvaluationPausedError):
        await run_trial(
            (provider, ModelConfig("openrouter", "model:free", 60000)),
            scenario.load("debug-shrine"),
            "travel_move",
            0,
            ledger,
            checkpoint="pr1",
        )
    assert ledger.spent == 1
    assert ledger.results()[0].status == "error"
    provider.generate_with_tools.assert_awaited_once()


def test_scenario_language_is_the_same_target_the_production_builder_reads():
    from app.ai.prompts.dm import build_dm_system_prompt

    sc = scenario.load("debug-thornhaven-it")
    assert sc.campaign.language == "it"
    assert "Italian (it)" in build_dm_system_prompt(sc.campaign)


async def test_sdk_retries_are_disabled_on_a_copy_not_the_cached_client(monkeypatch):
    from unittest.mock import MagicMock

    from live_calls import resolve_eval_generation

    from app.ai.providers.local import LocalProvider
    from app.ai.router import ModelConfig

    provider = LocalProvider.__new__(LocalProvider)
    client = MagicMock()
    provider.client = client
    monkeypatch.setattr(
        "live_calls.get_user_generation",
        AsyncMock(return_value=(provider, ModelConfig("openrouter", "personal", 60000))),
    )
    resolved, _ = await resolve_eval_generation(uuid.UUID(int=1), "model:free")
    assert resolved is not provider
    assert provider.client is client
    client.with_options.assert_called_once_with(max_retries=0)


async def test_actor_resume_identity_matches_the_actual_provider_request(tmp_path):
    import hashlib
    import json
    from dataclasses import replace

    from live_calls import run_trial

    from app.ai.router import ModelConfig

    provider = AsyncMock()
    provider.generate.return_value = '{"dialogue": "Ti ascolto, viaggiatore."}'
    config = ModelConfig("openrouter", "model:free", 60000)
    sc = scenario.load("debug-thornhaven-it")
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=2)
    first = await run_trial((provider, config), sc, "actor_language", 0, ledger, checkpoint="pr1")
    assert first.key.endswith(
        hashlib.sha256(json.dumps(first.request, sort_keys=True).encode()).hexdigest()
    )
    assert (
        await run_trial((provider, config), sc, "actor_language", 0, ledger, checkpoint="pr1")
        is None
    )
    await run_trial(
        (provider, replace(config, max_tokens=30000)),
        sc,
        "actor_language",
        0,
        ledger,
        checkpoint="pr1",
    )
    assert provider.generate.await_count == 2
