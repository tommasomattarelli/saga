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
from eval.support.dialogue_affinity import session_id_for_model

from app.ai.embedding_config import (
    EmbeddingCredential,
    ResolvedEmbedding,
    build_space,
    get_embedding_policy,
)
from app.ai.providers.embeddings_openai import OpenAICompatEmbeddingAdapter
from app.ai.providers.local import LocalProvider
from app.ai.router import get_user_generation


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
    assert (
        await auth_client.put("/api/settings/api-keys", json={"openrouter": "offline"})
    ).status_code == 200
    assert (
        await auth_client.patch(
            "/api/settings",
            json={
                "generation_provider": "openrouter",
                "generation_model": "offline/generation:free",
            },
        )
    ).status_code == 200
    _, dm_config = await get_user_generation(test_user["user"].id)
    assert dm_config.provider == "openrouter" and dm_config.destination_fingerprint
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
    generation_headers: list[str | None] = []

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
        generation_headers.append(request.headers.get("x-session-id"))
        schema = body["response_format"]["json_schema"]["schema"]
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
        result: dict[str, object]
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
    provider.provider_kind = "openrouter"
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

        async def embedding(owner, *, space):
            assert owner == test_user["user"].id
            assert space == resolved.space
            return resolved

        monkeypatch.setattr("eval.integrated_memory.execution.get_user_embedding", embedding)
        monkeypatch.setattr(
            "eval.integrated_memory.embedding_driver.get_user_embedding", embedding
        )
        monkeypatch.setattr(
            "app.ai.providers.base._providers",
            {("openrouter", "offline", None): provider},
        )
        monkeypatch.setattr("app.ai.embeddings.get_embedding_adapter", lambda _: adapter)
        monkeypatch.setattr(
            "eval.dialogue.limits.FreeRequestLimiter.wait", AsyncMock(return_value=0.0)
        )
        monkeypatch.setattr("app.memory.embedding_worker._pace", AsyncMock())

        async def resolve_dm(owner):
            assert owner == test_user["user"].id
            return provider, dm_config

        monkeypatch.setattr("app.core.dm.dm_nodes.get_user_generation", resolve_dm)
        await run_plan(plan, tmp_path, test_user["user"].id, authorized=True)
    assert calls == {"generation": 42 if sidecar else 31, "embedding": 3}
    outcome = json.loads((tmp_path / "run.json").read_text())
    assert outcome["state"] == "completed"
    assert outcome["counts"] == {**calls, "texts": 66}
    session_id = session_id_for_model(plan.session_scope, plan.generation_model or "")
    assert session_id != outcome["campaign_id"]
    assert generation_headers == [session_id] * calls["generation"]
    inputs = [json.loads(line) for line in (tmp_path / "inputs.jsonl").read_text().splitlines()]
    assert all(row["request"]["session_affinity"] == session_id for row in inputs)
    assert all(row["request_headers"]["x-session-id"] == session_id for row in inputs)
    outputs = [json.loads(line) for line in (tmp_path / "outputs.jsonl").read_text().splitlines()]
    assert all(row["session_affinity"] == session_id for row in outputs)
    assert all(row["request_headers"]["x-session-id"] == session_id for row in outputs)
    if sidecar:
        sidecar_outputs = [
            json.loads(line)
            for line in (tmp_path / "sidecar-outputs.jsonl").read_text().splitlines()
        ]
        assert all(row["session_affinity"] == session_id for row in sidecar_outputs)
        assert all(row["request_headers"]["x-session-id"] == session_id for row in sidecar_outputs)
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
