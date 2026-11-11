from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from eval.integrated_memory.ledger import AttemptScope, IntegratedLedger, LedgerBlockedError
from eval.integrated_memory.provider_guard import guard_generation

from app.ai.providers.local import LocalProvider


def _ledger(path: Path) -> IntegratedLedger:
    return IntegratedLedger(path, generation_cap=1, embedding_cap=0, text_cap=0, run_seal="plan")


def _scope() -> AttemptScope:
    return AttemptScope(
        run_id="run",
        campaign_id=uuid4(),
        source_turn_ids=(),
        input_hash="scope-input",
        role="facts",
        provider="openrouter",
        model="model-z",
    )


async def test_generation_guard_reserves_before_localprovider_sdk_and_disables_sdk_retries(
    tmp_path: Path,
) -> None:
    provider = LocalProvider(base_url="https://openrouter.ai/api/v1", api_key="controlled-test")
    response = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="ok"))],
        usage=None,
    )
    ledger = _ledger(tmp_path / "ledger.jsonl")
    limiter = Mock()
    limiter.wait = AsyncMock()
    with (
        patch(
            "openai.resources.chat.completions.AsyncCompletions.create",
            new=AsyncMock(return_value=response),
        ) as create,
        patch.object(
            provider.client, "with_options", wraps=provider.client.with_options
        ) as with_options,
        ledger.scope(_scope()),
    ):
        guarded = guard_generation(provider, ledger, limiter=limiter)
        assert (
            await guarded.generate("system", [{"role": "user", "content": "hi"}], "model-z")
            == "ok"
        )
    assert create.await_count == 1
    with_options.assert_called_once_with(max_retries=0)
    limiter.wait.assert_awaited_once_with("model-z")
    assert ledger.counts == {"generation": 1, "embedding": 0, "texts": 0}
    assert ledger._seen_ids


async def test_generation_guard_refuses_mismatched_scope_before_sdk(tmp_path: Path) -> None:
    provider = LocalProvider(base_url="https://openrouter.ai/api/v1", api_key="controlled-test")
    ledger = _ledger(tmp_path / "ledger.jsonl")
    with (
        patch(
            "openai.resources.chat.completions.AsyncCompletions.create", new=AsyncMock()
        ) as create,
        ledger.scope(_scope()),
        pytest.raises(LedgerBlockedError),
    ):
        await guard_generation(provider, ledger).generate("system", [], "other-model")
    create.assert_not_awaited()
