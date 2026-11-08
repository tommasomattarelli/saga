import uuid
from unittest.mock import AsyncMock

import eval.scenario_tools.scenario as scenario
import pytest
from eval.support.ledger import RequestLedger


async def test_paid_eval_needs_explicit_permission_before_profile_resolution(monkeypatch):
    from eval.support.live_calls import resolve_eval_generation

    from app.ai.router import ModelConfig

    resolve = AsyncMock(return_value=(AsyncMock(), ModelConfig("openrouter", "personal", 60000)))
    monkeypatch.setattr("eval.support.live_calls.get_user_generation", resolve)
    with pytest.raises(ValueError, match="explicit"):
        await resolve_eval_generation(uuid.UUID(int=1), "vendor/paid-model")
    resolve.assert_not_called()
    _, config = await resolve_eval_generation(
        uuid.UUID(int=1), "vendor/paid-model", allow_paid=True
    )
    assert config.model == "vendor/paid-model"
    assert config.max_tokens == 60000


async def test_unlisted_paid_model_is_rejected_without_contacting_catalog(monkeypatch):
    from eval.support.live_calls import validate_eval_models

    catalog = AsyncMock(side_effect=AssertionError("No network allowed"))
    monkeypatch.setattr("eval.support.live_calls.httpx.AsyncClient", catalog)
    with pytest.raises(ValueError, match="explicit"):
        await validate_eval_models(["vendor/unlisted"], {"vendor/allowed"})
    catalog.assert_not_called()


@pytest.mark.parametrize(
    "model,price,tools,valid",
    [
        ("vendor/free:free", "0", ["tools"], True),
        ("vendor/paid", "0.000001", ["tools"], True),
        ("vendor/free:free", "0.000001", ["tools"], False),
        ("vendor/paid", "nan", ["tools"], False),
        ("vendor/paid", "0.000001", [], False),
    ],
)
async def test_catalog_preflight_checks_prices_and_tools_without_generating(
    monkeypatch,
    model,
    price,
    tools,
    valid,
):
    import httpx
    from eval.support.live_calls import validate_eval_models

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "https://catalog.test"),
        json={
            "data": [
                {
                    "id": model,
                    "supported_parameters": tools,
                    "pricing": {"prompt": price, "completion": price},
                }
            ]
        },
    )
    monkeypatch.setattr("eval.support.live_calls.httpx.AsyncClient", lambda **kwargs: client)
    if valid:
        await validate_eval_models([model], {"vendor/paid"})
    else:
        with pytest.raises(ValueError, match="unavailable"):
            await validate_eval_models([model], {"vendor/paid"})
    client.get.assert_awaited_once()


async def test_eval_resolves_personal_configuration_without_mutating_it(monkeypatch):
    from eval.support.live_calls import resolve_eval_generation

    from app.ai.router import ModelConfig

    config = ModelConfig("openrouter", "personal-model", 60000)
    provider = AsyncMock()
    resolved = AsyncMock(return_value=(provider, config))
    monkeypatch.setattr("eval.support.live_calls.get_user_generation", resolved)
    result = await resolve_eval_generation(
        uuid.UUID(int=1), "nvidia/nemotron-3-ultra-550b-a55b:free"
    )
    resolved.assert_awaited_once_with(uuid.UUID(int=1))
    assert result[1].model.endswith(":free")
    assert result[1].max_tokens == 60000
    assert config.model == "personal-model"


async def test_resume_is_bound_to_checkpoint_model_and_exact_request(monkeypatch, tmp_path):
    from eval.support.live_calls import run_trial

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
    from eval.support.live_calls import EvaluationPausedError, run_trial

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

    from eval.support.live_calls import resolve_eval_generation

    from app.ai.providers.local import LocalProvider
    from app.ai.router import ModelConfig

    provider = LocalProvider.__new__(LocalProvider)
    client = MagicMock()
    provider.client = client
    monkeypatch.setattr(
        "eval.support.live_calls.get_user_generation",
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

    from eval.support.live_calls import run_trial

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
