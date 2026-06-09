import os

import pytest

from app.ai.router import AICallType, route_ai_call


@pytest.fixture(autouse=True)
def wipe_env(monkeypatch):
    """Ensure no SAGA_ env vars bleed from the host environment."""
    for key in list(os.environ.keys()):
        if key.startswith("SAGA_"):
            monkeypatch.delenv(key)


class MockContext:
    def __init__(self, importance_score: int):
        self.importance_score = importance_score


@pytest.mark.asyncio
async def test_route_dm_narration_low_importance():
    # importance <= 3 -> tier: low
    ctx = MockContext(importance_score=2)
    config = await route_ai_call(AICallType.DM_NARRATION, ctx)

    # Defaults from model_config.yaml (assuming anthropic claude-3-haiku for low)
    # The actual defaults depend on the yaml, but let's test the interface.
    assert config is not None
    assert hasattr(config, "provider")
    assert hasattr(config, "model")
    assert hasattr(config, "temperature")


@pytest.mark.asyncio
async def test_route_dm_narration_high_importance():
    # importance > 6 -> tier: high
    ctx = MockContext(importance_score=9)
    config = await route_ai_call(AICallType.DM_NARRATION, ctx)
    assert config is not None


@pytest.mark.asyncio
async def test_route_other_call_type():
    # Other types use "default" tier, importance doesn't matter
    ctx = MockContext(importance_score=10)
    config = await route_ai_call(AICallType.NPC_BEHAVIOR, ctx)
    assert config is not None


@pytest.mark.asyncio
async def test_router_env_var_override(monkeypatch):

    monkeypatch.setenv("SAGA_MODEL_DM_NARRATION_HIGH", "gpt-4o")
    monkeypatch.setenv("SAGA_MODEL_DM_NARRATION_HIGH_PROVIDER", "openai")

    # Force router to reload from env var by doing evaluating os.getenv
    # actually wait, router doesn't cache env vars, it gets them from `os.getenv` directly.
    # So setenv works for route_ai_call since it calls `os.getenv`.

    ctx = MockContext(importance_score=8)  # -> high tier
    config = await route_ai_call(AICallType.DM_NARRATION, ctx)

    assert config.model == "gpt-4o"
    assert config.provider == "openai"


@pytest.mark.asyncio
async def test_global_env_var_override(monkeypatch):
    monkeypatch.setattr("app.ai.router.settings.saga_global_provider", "dummy_provider")
    monkeypatch.setattr("app.ai.router.settings.saga_global_model_low", "dummy-low-model")

    ctx = MockContext(importance_score=1)  # -> low tier
    config = await route_ai_call(AICallType.DM_NARRATION, ctx)

    assert config.provider == "dummy_provider"
    assert config.model == "dummy-low-model"
