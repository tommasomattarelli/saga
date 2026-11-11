from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
from eval.memory.plan import digest
from eval.memory.runner import run_plan
from eval.support.dialogue_affinity import session_id_for_model
from openai import AsyncOpenAI

from app.ai.providers.local import LocalProvider
from app.ai.router import ModelConfig
from tests.unit.eval._memory_runner_support import memory_plan


def _payload(kind: str) -> str:
    result: dict[str, object]
    if kind == "global":
        result = {
            "story_so_far": "The party opened a door.",
            "open_threads": [],
            "relationships": [],
            "resolved_threads": [],
        }
    elif kind == "batch":
        result = {"facts": [], "summary": {"text": "The party opened a door."}}
    elif kind == "facts":
        result = {"facts": []}
    else:
        result = {"text": "The party opened a door."}
    return json.dumps(result)


@pytest.mark.asyncio
async def test_sdk_requests_carry_stable_model_affinity_reserved_in_ledger(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eval.support import live_calls

    models = ["vendor/alpha", "vendor/beta"]
    observed: list[tuple[str, str, str, str]] = []

    def providers_for(ledger_path):
        result: dict[str, LocalProvider] = {}
        for model in models:
            provider = LocalProvider("https://openrouter.ai/api/v1", "offline-test-key")

            async def handle(
                request: httpx.Request, *, selected_model: str = model
            ) -> httpx.Response:
                body = json.loads(request.content)
                session_id = request.headers.get("x-session-id", "")
                reservations = [
                    json.loads(line)
                    for line in ledger_path.read_text(encoding="utf-8").splitlines()
                    if json.loads(line).get("event") == "reserve"
                    and json.loads(line).get("model") == selected_model
                ]
                assert reservations
                assert reservations[-1]["request_headers"].get("x-session-id") == session_id
                kind = reservations[-1]["correlation"]["kind"]
                assert reservations[-1]["request_hash"] == digest(
                    {
                        "request": reservations[-1]["request"],
                        "headers": {"x-session-id": session_id},
                    }
                )
                observed.append((selected_model, session_id, kind, body["messages"][0]["content"]))
                content = _payload(kind)
                response = {
                    "id": "offline-response",
                    "object": "chat.completion",
                    "created": 1,
                    "model": selected_model,
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": content},
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
                return httpx.Response(200, json=response, request=request)

            transport = httpx.MockTransport(handle)
            sdk_http = httpx.AsyncClient(transport=transport)
            provider.client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key="offline-test-key",
                http_client=sdk_http,
            )
            result[model] = provider
        return result

    first = memory_plan(models=models, batches=2, repetitions=2)
    second = memory_plan(models=models, batches=2, repetitions=2, language="it")
    assert first.model_session_id(models[0]) == second.model_session_id(models[0])
    assert first.model_session_id(models[0]) != first.model_session_id(models[1])
    other_scope = memory_plan(models=models, scope="another-memory-scope")
    assert first.model_session_id(models[0]) != other_scope.model_session_id(models[0])

    async def execute(plan, directory) -> None:
        originals = providers_for(directory / "requests.jsonl")
        initial_clients = {model: provider.client for model, provider in originals.items()}

        async def resolve(_owner, model, *, allow_paid):
            assert allow_paid is False
            return originals[model], ModelConfig("openrouter", model, plan.output_cap)

        monkeypatch.setattr(live_calls, "resolve_eval_generation", resolve)
        await run_plan(plan, directory, uuid4(), authorized=True)
        assert all(
            provider.client is initial_clients[model] for model, provider in originals.items()
        )
        assert all(
            "x-session-id" not in provider.client.default_headers
            for provider in originals.values()
        )
        await originals[models[0]].client.close()
        await originals[models[1]].client.close()

    await execute(first, tmp_path / "first")
    first_observed = observed.copy()
    observed.clear()
    await execute(second, tmp_path / "second")

    assert len(first_observed) == first.call_budget == 28
    assert len(observed) == second.call_budget == 28
    for directory in (tmp_path / "first", tmp_path / "second"):
        rows = [
            json.loads(line)
            for line in (directory / "outputs.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert all(row["session_id"] for row in rows)
    for plan, requests in ((first, first_observed), (second, observed)):
        for model in models:
            matching = [entry for entry in requests if entry[0] == model]
            assert len(matching) == 14
            assert {entry[1] for entry in matching} == {plan.model_session_id(model)}
            assert {entry[2] for entry in matching} == {"batch", "summary", "facts", "global"}
    assert all(
        session_id_for_model("test-memory-scope", model) == first.model_session_id(model)
        for model in models
    )
