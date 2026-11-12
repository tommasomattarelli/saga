import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import openai
import pytest
from eval.integrated_memory.ledger import AttemptScope, IntegratedLedger, LedgerBlockedError
from eval.integrated_memory.plan import (
    load_plan,
    prepare_plan,
    resolve_effective_embedding,
    write_plan,
)
from eval.integrated_memory.provider_guard import guard_embedding_attempts

from app.ai.embedding_config import (
    EmbeddingCredential,
    ResolvedEmbedding,
    build_space,
    get_embedding_policy,
)
from app.ai.providers.embeddings_openai import OpenAICompatEmbeddingAdapter
from app.exceptions import AIProviderError
from app.memory.job_coverage import coverage_counts
from tests.unit.eval._integrated_sources import integrated_source


@pytest.mark.parametrize(
    ("total", "expected"),
    [(0, (0, 0)), (8, (0, 0)), (11, (0, 0)), (12, (1, 0)), (20, (3, 1)), (52, (11, 9))],
)
def test_compaction_targets_preserve_raw_and_intermediate_windows(total, expected) -> None:
    assert coverage_counts(total, 8, 4, 2) == expected


def test_fingerprint_cache_detects_content_and_membership_changes(tmp_path, monkeypatch) -> None:
    from eval.integrated_memory.plan import _fingerprint

    root = tmp_path / "backend"
    (root / "app").mkdir(parents=True)
    source = root / "app" / "a.py"
    source.write_text("A = 1\n")
    config = root.parent / "saga.config.yaml"
    config.write_text("value: 1\n")
    with patch.object(Path, "read_bytes", autospec=True, side_effect=Path.read_bytes) as read:
        before = _fingerprint(root)
        reads = read.call_count
        assert _fingerprint(root) == before and read.call_count == reads
        stat = source.stat()
        source.write_text("B = 2\n")
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        changed = _fingerprint(root)
        assert changed != before
        config.write_text("value: 2\n")
        after_config = _fingerprint(root)
        assert after_config != changed
        changed = after_config
        added = root / "app" / "b.py"
        added.write_text("B = 1\n")
        assert _fingerprint(root) != changed
        added.unlink()
        assert _fingerprint(root) == changed


def test_retry_reduction_is_frozen_without_changing_profile_and_rejects_drift(
    tmp_path, monkeypatch
) -> None:
    import eval.integrated_memory.plan as module

    configured = get_embedding_policy()
    space = build_space("openrouter", "openai/text-embedding-3-small")
    plan = prepare_plan(
        sources=integrated_source(), run_id="retry", embedding_space=space, embedding_max_retries=1
    )
    assert plan.embedding_policy == replace(configured, max_retries=1)
    write_plan(plan, tmp_path)
    assert load_plan(tmp_path) == plan
    resolved = ResolvedEmbedding(space, EmbeddingCredential("test", "personal"), configured)
    assert resolve_effective_embedding(plan, resolved).policy.max_retries == 1
    assert resolved.policy == configured
    for cap in (-1, configured.max_retries + 1):
        with pytest.raises(ValueError):
            prepare_plan(sources=integrated_source(), run_id="invalid", embedding_max_retries=cap)
    with pytest.raises(ValueError, match="configured policy"):
        resolve_effective_embedding(
            plan, replace(resolved, policy=replace(configured, max_retries=0))
        )
    monkeypatch.setattr(module, "get_embedding_policy", lambda: replace(configured, batch_size=16))
    with pytest.raises(ValueError, match="embedding policy changed"):
        load_plan(tmp_path)


@pytest.mark.parametrize("failures", [1, 3])
async def test_frozen_retry_limit_counts_attempts_and_stops_before_a_third(
    tmp_path, failures
) -> None:
    calls = 0

    async def respond(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls <= failures:
            raise openai.APIConnectionError(request=httpx.Request("POST", "https://provider.test"))
        return SimpleNamespace(
            data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])], model_extra=None
        )

    policy = get_embedding_policy()
    ledger = IntegratedLedger(
        tmp_path / "ledger", generation_cap=0, embedding_cap=3, text_cap=3, run_seal="s"
    )
    scope = AttemptScope(
        run_id="r",
        campaign_id=uuid4(),
        source_turn_ids=(),
        input_hash="h",
        role="embedding",
        provider="openrouter",
        model="m",
    )
    adapter = OpenAICompatEmbeddingAdapter(
        provider="openrouter",
        api_key="test",
        base_url="https://openrouter.ai/api/v1",
        policy=policy,
    )
    with (
        patch("openai.resources.embeddings.AsyncEmbeddings.create", side_effect=respond),
        patch("app.ai.embedding_validation.asyncio.sleep", new=AsyncMock()),
        ledger.scope(scope),
        guard_embedding_attempts(
            ledger,
            model="m",
            provider="openrouter",
            texts=["t"],
            policy=replace(policy, max_retries=1),
        ),
    ):
        if failures == 1:
            await adapter.embed("m", ["t"])
            ledger.ensure_healthy()
        else:
            with pytest.raises((AIProviderError, LedgerBlockedError)):
                await adapter.embed("m", ["t"])
            with pytest.raises(LedgerBlockedError):
                ledger.ensure_healthy()
    assert calls == ledger.counts["embedding"] == ledger.counts["texts"] == 2
