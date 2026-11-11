import json
from pathlib import Path
from uuid import uuid4

import pytest
from eval.integrated_memory.ledger import AttemptScope, IntegratedLedger, LedgerBlockedError


def test_reserves_each_kind_before_attempt_and_persists_counts(tmp_path: Path) -> None:
    ledger = IntegratedLedger(
        tmp_path / "ledger.jsonl", generation_cap=1, embedding_cap=2, text_cap=3, run_seal="seal"
    )
    with ledger.scope(
        AttemptScope(
            run_id="r",
            campaign_id=uuid4(),
            job_id=uuid4(),
            batch_id=uuid4(),
            source_turn_ids=(uuid4(),),
            input_hash="h",
            role="facts",
            provider="test",
            model="test",
        )
    ):
        ledger.reserve("generation", {"model": "test", "provider": "test"}, texts=0)
    ledger.complete()
    with ledger.scope(
        AttemptScope(
            run_id="r",
            campaign_id=uuid4(),
            source_turn_ids=(uuid4(),),
            input_hash="scope-hash",
            role="embedding",
            provider="openrouter",
            model="embed",
        )
    ):
        ledger.reserve(
            "embedding",
            {
                "model": "embed",
                "provider": "openrouter",
                "input_hash": "request-hash",
                "space": "openrouter",
            },
            texts=2,
        )
        ledger.complete()
    assert ledger.counts == {"generation": 1, "embedding": 1, "texts": 2}
    loaded = IntegratedLedger(
        tmp_path / "ledger.jsonl", generation_cap=1, embedding_cap=2, text_cap=3, run_seal="seal"
    )
    assert loaded.counts == ledger.counts
    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    embedding = next(row for row in rows if row.get("kind") == "embedding")
    assert embedding["metadata"]["input_hash"] == "scope-hash"
    assert embedding["metadata"]["request_input_hash"] == "request-hash"


def test_pending_or_malformed_ledger_blocks_resume(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = IntegratedLedger(path, generation_cap=2, embedding_cap=2, text_cap=2, run_seal="seal")
    ledger.reserve("generation", {"model": "test"}, texts=0)
    with pytest.raises(LedgerBlockedError):
        IntegratedLedger(path, generation_cap=2, embedding_cap=2, text_cap=2, run_seal="seal")
    path.write_text("not-json\n")
    with pytest.raises(LedgerBlockedError):
        IntegratedLedger(path, generation_cap=2, embedding_cap=2, text_cap=2, run_seal="seal")


def test_budget_exhaustion_is_fail_closed(tmp_path: Path) -> None:
    ledger = IntegratedLedger(
        tmp_path / "ledger.jsonl", generation_cap=1, embedding_cap=2, text_cap=2, run_seal="seal"
    )
    ledger.reserve("generation", {"provider": "openrouter", "model": "m"}, texts=0)
    ledger.fail()
    with pytest.raises(LedgerBlockedError):
        ledger.reserve("generation", {}, texts=0)


def test_caps_seal_and_failure_latch(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = IntegratedLedger(path, generation_cap=1, embedding_cap=1, text_cap=1, run_seal="seal")
    ledger.reserve("generation", {"provider": "openrouter", "model": "m"}, texts=0)
    ledger.fail()
    with pytest.raises(LedgerBlockedError):
        IntegratedLedger(path, generation_cap=2, embedding_cap=1, text_cap=1, run_seal="seal")
    with pytest.raises(LedgerBlockedError):
        IntegratedLedger(path, generation_cap=1, embedding_cap=1, text_cap=1, run_seal="other")
    with pytest.raises(LedgerBlockedError):
        ledger.ensure_healthy()

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    forged = {**rows[1], "attempt_id": "another", "kind": "embedding"}
    with path.open("a") as handle:
        handle.write(json.dumps(forged) + "\n")
        handle.write(json.dumps({"event": "complete", "attempt_id": "another"}) + "\n")
    with pytest.raises(LedgerBlockedError):
        IntegratedLedger(path, generation_cap=1, embedding_cap=1, text_cap=1, run_seal="seal")


def test_invalid_caps_and_cancelled_attempt_block(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        IntegratedLedger(
            tmp_path / "bad", generation_cap=-1, embedding_cap=1, text_cap=1, run_seal="seal"
        )
    ledger = IntegratedLedger(
        tmp_path / "cancel", generation_cap=1, embedding_cap=1, text_cap=1, run_seal="seal"
    )
    ledger.reserve("generation", {"provider": "openrouter", "model": "m"}, texts=0)
    ledger.cancel()
    with pytest.raises(LedgerBlockedError):
        ledger.ensure_healthy()


def test_retry_failure_is_allowed_in_process_but_not_after_interruption(tmp_path: Path) -> None:
    path = tmp_path / "retry-ledger.jsonl"
    ledger = IntegratedLedger(path, generation_cap=0, embedding_cap=2, text_cap=2, run_seal="seal")
    ledger.reserve("embedding", {"provider": "openrouter", "model": "m"}, texts=1)
    ledger.fail(retrying=True)
    ledger.reserve("embedding", {"provider": "openrouter", "model": "m"}, texts=1)
    ledger.complete()
    assert ledger.counts["embedding"] == 2

    interrupted_path = tmp_path / "interrupted.jsonl"
    interrupted = IntegratedLedger(
        interrupted_path, generation_cap=0, embedding_cap=3, text_cap=3, run_seal="seal"
    )
    interrupted.reserve("embedding", {"provider": "openrouter", "model": "m"}, texts=1)
    interrupted.fail(retrying=True)
    with pytest.raises(LedgerBlockedError):
        IntegratedLedger(
            interrupted_path, generation_cap=0, embedding_cap=3, text_cap=3, run_seal="seal"
        )
