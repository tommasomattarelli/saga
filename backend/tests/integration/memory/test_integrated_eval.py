import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import openai
import pytest
from eval.integrated_memory.plan import prepare_plan, write_plan
from eval.integrated_memory.runner import run_plan
from eval.memory_scenarios.build import build_scenario

from app.ai.embedding_config import (
    EmbeddingCredential,
    ResolvedEmbedding,
    build_space,
    get_embedding_policy,
)
from app.ai.providers.embeddings_openai import OpenAICompatEmbeddingAdapter
from app.ai.providers.local import LocalProvider
from app.ai.router import ModelConfig


@pytest.mark.parametrize("sidecar", [False, True])
async def test_guarded_integrated_runner_uses_real_api_jobs_and_embedding_queue_offline(
    configured_generation,
    auth_client,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
    assert_no_db_held,
    tmp_path: Path,
    sidecar: bool,
) -> None:
    original_profile = (await auth_client.get("/api/settings")).json()
    source = await asyncio.to_thread(build_scenario, batch_size=4, plan=(8, 2, 9))
    space = build_space("openrouter", "offline/embedding")
    plan = prepare_plan(
        sources=source.sources.model_dump(mode="json"),
        run_id=f"offline-system-{sidecar}",
        generation_model="offline/generation:free",
        generation_request_cap=42 if sidecar else 31,
        embedding_space=space,
        embedding_request_cap=3,
        embedding_text_cap=66,
        embedding_max_retries=1,
        unified_sidecar=sidecar,
    )
    write_plan(plan, tmp_path)
    calls = {"generation": 0, "embedding": 0}

    def respond(request: httpx.Request) -> httpx.Response:
        assert_no_db_held()
        body = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            calls["embedding"] += 1
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": index, "embedding": [1.0, 0.25, 0.5]}
                        for index, _ in enumerate(body["input"])
                    ]
                },
            )
        assert request.url.path.endswith("/chat/completions")
        calls["generation"] += 1
        schema = json.loads(body["messages"][0]["content"].rsplit("\n", 1)[-1])
        properties = schema["properties"]
        facts = [
            {
                "content": f"Authored test event {index}.",
                "category": "event",
                "assertion_type": "occurrence",
                "entities": [],
                "attribution": [],
                "source_turns": ["t1"],
                "temporal_references": [],
                "importance": {"level": "ordinary", "reason": "Recorded test event."},
            }
            for index in range(6)
        ]
        if "story_so_far" in properties:
            result = {
                "story_so_far": "The story continues.",
                "open_threads": [],
                "relationships": [],
                "resolved_threads": [],
            }
        elif "summary" in properties:
            result = {"summary": {"text": "Integrated summary."}, "facts": facts}
        elif "facts" in properties:
            result = {"facts": facts}
        else:
            result = {"text": "Integrated summary."}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": json.dumps(result)},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    resolved = ResolvedEmbedding(
        space, EmbeddingCredential("offline", "personal"), get_embedding_policy()
    )
    provider = object.__new__(LocalProvider)
    adapter = object.__new__(OpenAICompatEmbeddingAdapter)
    adapter.provider, adapter.policy = "openrouter", resolved.policy
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        sdk = openai.AsyncOpenAI(
            api_key="offline",
            base_url="https://openrouter.ai/api/v1",
            max_retries=0,
            http_client=http,
        )
        provider.client = sdk
        adapter.client = sdk

        async def generation(owner, model, *, allow_paid=False):
            assert owner == test_user["user"].id
            return provider, ModelConfig("openrouter", model, plan.output_cap)

        async def embedding(owner, *, space):
            assert owner == test_user["user"].id
            assert space == resolved.space
            return resolved

        monkeypatch.setattr("eval.integrated_memory.execution.resolve_eval_generation", generation)
        monkeypatch.setattr("eval.integrated_memory.execution.get_user_embedding", embedding)
        monkeypatch.setattr(
            "eval.integrated_memory.embedding_driver.get_user_embedding", embedding
        )
        monkeypatch.setattr("app.ai.embeddings.get_embedding_adapter", lambda _: adapter)
        monkeypatch.setattr(
            "eval.dialogue.limits.FreeRequestLimiter.wait", AsyncMock(return_value=0.0)
        )
        monkeypatch.setattr("app.memory.embedding_worker._pace", AsyncMock())
        await run_plan(plan, tmp_path, test_user["user"].id, authorized=True)
    assert calls == {"generation": 42 if sidecar else 31, "embedding": 3}
    outcome = json.loads((tmp_path / "run.json").read_text())
    assert outcome["state"] == "completed"
    assert outcome["counts"] == {**calls, "texts": 66}
    assert {path.name for path in tmp_path.iterdir()} == {
        "manifest.json",
        "run-start.json",
        "run.json",
        "requests.jsonl",
        "turns.jsonl",
        "inputs.jsonl",
        "outputs.jsonl",
        "source-evidence.json",
        "embedding-inputs.jsonl",
        "campaign.json",
    } | ({"sidecar-inputs.jsonl", "sidecar-outputs.jsonl"} if sidecar else set())
    profile = (await auth_client.get("/api/settings")).json()
    for key in ("generation_provider", "generation_model", "generation_local_endpoint"):
        assert profile[key] == original_profile[key]
    evidence = json.loads((tmp_path / "source-evidence.json").read_text())
    assert len(evidence["turns"]) == 52
    assert len(evidence["batches"]) == 11
    with pytest.raises(ValueError, match="automatic replay is disabled"):
        await run_plan(plan, tmp_path, test_user["user"].id, authorized=True)
    assert calls == {"generation": 42 if sidecar else 31, "embedding": 3}
