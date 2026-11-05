import asyncio
import json
from pathlib import Path
from uuid import UUID

import httpx
import openai
import pytest
from cache import probe
from cache.plan import MODELS, build_plan, write_plan
from cache.runner import run_block
from ledger import RequestLedger

from app.ai.providers.local import LocalProvider


async def test_prepare_is_offline_and_tampered_manifest_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Offline preparation or stale plan reached the network/profile")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    monkeypatch.setattr(probe, "resolve_eval_generation", forbidden)
    monkeypatch.setattr(probe, "validate_eval_models", forbidden)
    monkeypatch.setattr(
        "sys.argv",
        [
            "probe",
            "prepare",
            "--model",
            MODELS[0],
            "--phase",
            "replay",
            "--run-id",
            "test",
            "--out",
            str(tmp_path),
        ],
    )
    await probe.main()
    path = tmp_path / "manifest.json"
    raw = json.loads(path.read_text())
    raw["payloads"]["A"]["system_prompt"] += "changed"
    path.write_text(json.dumps(raw))
    monkeypatch.setattr(
        "sys.argv",
        [
            "probe",
            "run",
            "--out",
            str(tmp_path),
            "--user",
            str(UUID(int=1)),
        ],
    )
    with pytest.raises(SystemExit) as error:
        await probe.main()
    assert error.value.code == 2
    assert not (tmp_path / "started.json").exists()


@pytest.mark.parametrize("failure", ["metadata", "upstream", "interrupted"])
async def test_missing_usage_metadata_and_interruptions_stay_visible(
    tmp_path: Path, failure: str
) -> None:
    plan = await build_plan(MODELS[0], "identical", "test", 1024)
    posts = 0
    gets = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal posts, gets
        if request.method == "GET":
            gets += 1
            return httpx.Response(404, json={"error": {"message": "not ready"}})
        posts += 1
        if failure == "interrupted" and posts == 2:
            raise asyncio.CancelledError
        if failure == "upstream":
            return httpx.Response(200, json={"error": {"message": "internal private detail"}})
        return httpx.Response(
            200,
            json={
                "id": f"gen-test-{posts}",
                "model": plan.model,
                "object": "chat.completion",
                "created": 1,
                "usage": None,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "ignored",
                        },
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = LocalProvider(api_key="test", base_url="https://openrouter.ai/api/v1")
        await provider.client.close()
        provider.client = openai.AsyncOpenAI(
            api_key="test",
            base_url="https://openrouter.ai/api/v1",
            http_client=http,
        )
        if failure == "interrupted":
            with pytest.raises(asyncio.CancelledError):
                await run_block(plan, provider, tmp_path, UUID(int=1))
        else:
            await run_block(plan, provider, tmp_path, UUID(int=1))

    ledger = RequestLedger(tmp_path / "requests.jsonl")
    if failure == "metadata":
        assert posts == gets == ledger.spent == 8
        assert all(a.usage[0]["cached_input_tokens"] is None for a in ledger.results())
        assert (tmp_path / "metadata.jsonl").read_text().count("unavailable") == 8
        assert (tmp_path / "report.md").read_text().count("4 missing pairs") == 2
    elif failure == "upstream":
        assert posts == ledger.spent == 1 and gets == 0
        assert ledger.results()[0].status == "error"
        assert "private detail" not in (tmp_path / "requests.jsonl").read_text()
    else:
        assert posts == ledger.spent == 2 and gets == 0
        assert len(ledger.interrupted()) == 1
        assert "Interrupted: 1" in (tmp_path / "report.md").read_text()


async def test_preparation_never_overwrites_a_different_manifest(tmp_path: Path) -> None:
    plan = await build_plan(MODELS[0], "identical", "test", 1024)
    write_plan(plan, tmp_path)
    before = (tmp_path / "manifest.json").read_bytes()
    changed = await build_plan(MODELS[0], "replay", "test", 1024)
    with pytest.raises(ValueError, match="Manifest changed"):
        write_plan(changed, tmp_path)
    assert (tmp_path / "manifest.json").read_bytes() == before
