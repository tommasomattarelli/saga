import json
from pathlib import Path
from uuid import UUID

import httpx
import openai
import pytest
from cache.payloads import build_payloads
from cache.plan import MODELS, build_plan
from cache.runner import run_block
from ledger import RequestLedger

from app.ai.providers.local import LocalProvider


async def test_payloads_use_real_tool_effects_without_generation(monkeypatch):
    async def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Offline assembly contacted a provider")

    monkeypatch.setattr(LocalProvider, "generate", forbidden)
    monkeypatch.setattr(LocalProvider, "generate_with_tools", forbidden)
    payloads = await build_payloads(MODELS[0], 1024)
    again = await build_payloads(MODELS[0], 1024)
    assert payloads == again
    first, second = payloads["A"], payloads["B"]
    assert first.max_tokens == second.max_tokens == 1024
    assert second.messages[:-2] == first.messages
    assert second.messages[-2]["role"] == "assistant"
    assert second.messages[-1]["role"] == "tool"
    assert "[[npc:Aldric:1]]" in second.messages[-1]["content"]
    assert first.system_prompt != second.system_prompt
    assert "[[npc:Aldric:1]]" in second.system_prompt
    assert first.tools == second.tools


async def test_matrix_is_eight_calls_and_only_affinity_changes():
    plan = await build_plan(MODELS[0], "identical", "probe-one", 1024)
    assert len(plan.requests) == 8
    assert [r.payload for r in plan.requests] == ["A"] * 8
    ids = [r.session_id for r in plan.requests]
    assert ids[0] == ids[1] != ids[2] == ids[3]
    assert len(set(ids[4:])) == 1
    assert len(set(ids)) == 3
    replay = await build_plan(MODELS[0], "replay", "probe-one", 1024)
    assert [r.payload for r in replay.requests] == ["A", "B"] * 4
    assert not set(ids) & {r.session_id for r in replay.requests}
    other = await build_plan(MODELS[1], "identical", "probe-one", 1024)
    assert not set(ids) & {r.session_id for r in other.requests}


def completion(model: str, index: int) -> dict[str, object]:
    return {
        "id": f"gen-cache-{index}",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "length",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "ignored",
                            "type": "function",
                            "function": {
                                "name": "invoke_npc",
                                "arguments": '{"name":',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 8000,
            "completion_tokens": 1024,
            "total_tokens": 9024,
            "prompt_tokens_details": {"cached_tokens": 4096, "cache_write_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 1000},
            "cost": 0.001,
        },
    }


async def test_wire_matches_production_and_live_outputs_never_drive_replay(tmp_path: Path):
    plan = await build_plan(MODELS[0], "replay", "probe-one", 1024)
    ledger_path = tmp_path / "requests.jsonl"
    bodies: list[object] = []
    headers: list[str | None] = []
    order: list[str] = []
    check_reservations = False

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            order.append("metadata")
            assert len(bodies) == 8
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": request.url.params["id"],
                        "provider_name": "Example",
                        "provider_responses": [{"endpoint_id": "ep-1", "status": 200}],
                        "total_cost": 0.001,
                    }
                },
            )
        if check_reservations:
            assert RequestLedger(ledger_path).spent == len(bodies) + 1
        order.append("generation")
        bodies.append(json.loads(request.content))
        headers.append(request.headers.get("x-session-id"))
        data = completion(plan.model, len(bodies))
        if not check_reservations:
            data["choices"] = [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "ok",
                    },
                }
            ]
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = LocalProvider(api_key="test", base_url="https://openrouter.ai/api/v1")
        await provider.client.close()
        provider.client = openai.AsyncOpenAI(
            api_key="test",
            base_url="https://openrouter.ai/api/v1",
            http_client=http,
        )
        await provider.generate_with_tools(**plan.payloads["A"].model_dump())
        production_body = bodies.pop()
        headers.clear()
        order.clear()
        check_reservations = True
        await run_block(plan, provider, tmp_path, UUID(int=1))
        assert provider.client.max_retries == 2
        assert "x-session-id" not in provider.client.default_headers

    assert bodies[0] == production_body
    assert bodies == [plan.payloads[r.payload].body() for r in plan.requests]
    assert headers == [r.session_id for r in plan.requests]
    assert order == ["generation"] * 8 + ["metadata"] * 8
    attempts = RequestLedger(ledger_path).results()
    assert len(attempts) == 8
    assert all(a.status == "ok" and a.response["finish_reason"] == "length" for a in attempts)
    assert all(a.usage[0]["cached_input_tokens"] == 4096 for a in attempts)
    assert "Example" in (tmp_path / "report.md").read_text()
    with pytest.raises(ValueError, match="already started"):
        await run_block(plan, provider, tmp_path, UUID(int=1))


async def test_http_error_stops_without_sdk_retries_and_records_attempt(tmp_path: Path):
    plan = await build_plan(MODELS[0], "identical", "probe-one", 1024)
    calls = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"error": {"message": "private detail"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = LocalProvider(api_key="test", base_url="https://openrouter.ai/api/v1")
        await provider.client.close()
        provider.client = openai.AsyncOpenAI(
            api_key="test",
            base_url="https://openrouter.ai/api/v1",
            http_client=http,
        )
        await run_block(plan, provider, tmp_path, UUID(int=1))
    assert calls == 1
    ledger = RequestLedger(tmp_path / "requests.jsonl")
    assert ledger.spent == 1 and not ledger.interrupted()
    assert ledger.results()[0].status == "error"
    assert "private detail" not in (tmp_path / "requests.jsonl").read_text()
