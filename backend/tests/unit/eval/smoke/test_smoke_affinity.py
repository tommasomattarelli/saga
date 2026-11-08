from pathlib import Path

import httpx
import openai
from eval.scenario_tools.scenario import load
from eval.support.dialogue_affinity import session_id_for_model
from eval.support.ledger import RequestLedger
from eval.support.live_calls import run_trial

from app.ai.providers.local import LocalProvider
from app.ai.router import ModelConfig


async def test_smoke_dm_and_actor_repetitions_bind_header_to_checkpoint_identity(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "gen-test",
                "object": "chat.completion",
                "created": 0,
                "model": "m:free",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"status":"silent","lines":[]}',
                        },
                    }
                ],
            },
        )

    provider = LocalProvider("https://openrouter.ai/api/v1", "test")
    await provider.client.close()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider.client = openai.AsyncOpenAI(
            api_key="test", base_url="https://openrouter.ai/api/v1", http_client=http
        )
        generation = provider, ModelConfig("openrouter", "m:free", 60000)
        session = session_id_for_model("checkpoint", "m:free")
        ledger = RequestLedger(tmp_path / "calls.jsonl", budget=4)
        for repetition in range(2):
            for probe in ("npc_speaks", "actor_language"):
                await run_trial(
                    generation,
                    load("debug-thornhaven"),
                    probe,
                    repetition,
                    ledger,
                    checkpoint="checkpoint",
                    session_id=session,
                )
        assert len(requests) == ledger.spent == 4
        assert {r.headers["x-session-id"] for r in requests} == {session}
        assert "x-session-id" not in provider.client.default_headers
        for row in ledger.results():
            assert row.request_headers == {"x-session-id": session}
            assert row.request_hash and row.key.endswith(row.request_hash)
        assert (
            await run_trial(
                generation,
                load("debug-thornhaven"),
                "npc_speaks",
                0,
                ledger,
                checkpoint="checkpoint",
                session_id=session,
            )
            is None
        )
        assert len(requests) == 4
