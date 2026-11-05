import asyncio
import csv
import hashlib
import io
import json
import uuid
from collections.abc import AsyncIterator

import dialogue_suite
import httpx
import pytest
from dialogue_evidence import read_evidence
from dialogue_execution import run_models
from dialogue_plan import manifest, trial_key
from dialogue_requests import SuiteProvider
from dialogue_trial import run_case
from ledger import RequestLedger
from openai import AsyncOpenAI, InternalServerError
from usage_report import usage_csv

from app.ai.providers.local import LocalProvider
from app.ai.router import ModelConfig


@pytest.fixture
async def provider() -> AsyncIterator[tuple[LocalProvider, list[httpx.Request]]]:
    requests: list[httpx.Request] = []

    async def complete(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        content = (
            '{"status":"speaking","lines":["I do not know you."]}'
            if "response_format" in body
            else "The square is quiet."
        )
        return httpx.Response(
            200,
            json={
                "id": f"response-{len(requests)}",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 4096,
                    "completion_tokens": 10,
                    "total_tokens": 4106,
                    "prompt_tokens_details": {"cached_tokens": 2048},
                },
            },
        )

    transport = httpx.AsyncClient(transport=httpx.MockTransport(complete))
    local = LocalProvider("https://openrouter.ai/api/v1", "test-key")
    await local.client.close()
    local.client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
        http_client=transport,
        max_retries=0,
        default_headers={"X-Eval-App": "preserved"},
    )
    try:
        yield local, requests
    finally:
        await local.client.close()


def test_session_identity_is_stable_per_suite_and_model_not_trial() -> None:
    from dialogue_affinity import session_id_for_model
    from dialogue_plan import digest

    plan = manifest(
        models=["vendor/a:free", "vendor/b:free"],
        case_names=["npc_followup", "actor_en"],
        runs=2,
        session_affinity=True,
    )
    identifiers = [session_id_for_model(digest(plan), model) for model in plan["models"]]
    assert len(set(identifiers)) == 2
    for model, identifier in zip(plan["models"], identifiers, strict=True):
        assert identifier == session_id_for_model(
            digest(
                manifest(
                    models=plan["models"],
                    case_names=list(plan["cases"]),
                    runs=2,
                )
            ),
            model,
        )
        assert str(uuid.UUID(identifier)) == identifier
        assert len(identifier) <= 256
        assert "vendor" not in identifier
        assert identifier != session_id_for_model("another-checkpoint", model)


async def test_parallel_trial_clients_keep_one_header_for_dm_and_actors_without_mutation(
    provider: tuple[LocalProvider, list[httpx.Request]],
    tmp_path,
) -> None:
    from dialogue_affinity import session_id_for_model

    original, requests = provider
    ledger = RequestLedger(tmp_path / "requests.jsonl", budget=3)
    traces = [
        SuiteProvider(
            original,
            ledger,
            key=key,
            case="fixture",
            model="vendor/a:free",
            run=0,
            commit="commit",
            ceiling=2,
            session_id=session_id_for_model(key, "vendor/a:free"),
        )
        for key in ("trial-a", "trial-b")
    ]
    await asyncio.gather(
        traces[0].generate_with_tools("DM-A", [], [], "vendor/a:free"),
        traces[1].generate("NPC-B", [], "vendor/a:free", json_mode=True),
        traces[0].generate("NPC-A", [], "vendor/a:free", json_mode=True),
    )
    for request in requests:
        system = json.loads(request.content)["messages"][0]["content"]
        key = "trial-b" if system.endswith("B") else "trial-a"
        assert request.headers["x-session-id"] == session_id_for_model(key, "vendor/a:free")
        assert request.headers["x-eval-app"] == "preserved"
    assert "x-session-id" not in original.client.default_headers
    assert original.client.max_retries == 0
    assert all(
        trace.provider is not original and trace.provider.client.max_retries == 0
        for trace in traces
    )
    for attempt in ledger.results():
        assert set(attempt.request_headers) == {"x-session-id"}
        assert attempt.usage[0]["cached_input_tokens"] == 2048
        fingerprint = {"body": attempt.request, "headers": attempt.request_headers}
        assert (
            attempt.request_hash
            == hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
        )
    replay = RequestLedger(ledger.path)
    assert [row.request_headers for row in replay.results()] == [
        row.request_headers for row in ledger.results()
    ]
    rows = list(csv.DictReader(io.StringIO(usage_csv([vars(row) for row in replay.results()]))))
    assert {row["session_id"] for row in rows} == {
        session_id_for_model("trial-a", "vendor/a:free"),
        session_id_for_model("trial-b", "vendor/a:free"),
    }


async def test_affinity_is_opt_in_and_default_transport_and_hash_are_unchanged(
    provider: tuple[LocalProvider, list[httpx.Request]],
    tmp_path,
) -> None:
    original, requests = provider
    ledger = RequestLedger(tmp_path / "requests.jsonl", budget=1)
    trace = SuiteProvider(
        original,
        ledger,
        key="trial",
        case="fixture",
        model="vendor/a:free",
        run=0,
        commit="commit",
        ceiling=1,
    )
    await trace.generate("system", [], "vendor/a:free")
    assert trace.provider is original
    assert "x-session-id" not in requests[0].headers
    row = ledger.results()[0]
    assert row.request_headers == {}
    assert (
        row.request_hash
        == hashlib.sha256(json.dumps(row.request, sort_keys=True).encode()).hexdigest()
    )


async def test_runner_shares_session_across_cases_repetitions_and_resume(
    provider: tuple[LocalProvider, list[httpx.Request]],
    tmp_path,
) -> None:
    from dialogue_affinity import session_id_for_model
    from dialogue_plan import digest

    original, requests = provider
    model = "vendor/a:free"
    plan = manifest(
        models=[model],
        case_names=["npc_followup", "actor_en", "two_npc_conversation"],
        runs=2,
    )
    completed: dict[str, dict] = {}
    output = tmp_path / "trials.jsonl"
    ledger = RequestLedger(tmp_path / "requests.jsonl", budget=16)
    await run_models(
        plan,
        completed,
        ledger,
        output,
        {model: (original, ModelConfig("openrouter", model, 60000))},
        uuid.uuid4(),
        "commit",
        run_case,
        {},
    )
    evidence, interrupted = read_evidence(output)
    assert not interrupted and len(evidence) == 6
    conversation_key = trial_key(plan, "two_npc_conversation", model, 0)
    for row in evidence.values():
        assert row["session_id"] == session_id_for_model(digest(plan), model)
    conversation = [row for row in ledger.results() if row.key.startswith(conversation_key)]
    assert len(conversation) == 2
    assert all(
        row.request_headers["x-session-id"] == session_id_for_model(digest(plan), model)
        for row in conversation
    )
    assert len({request.headers["x-session-id"] for request in requests}) == 1
    before = len(requests)
    await run_models(
        plan,
        evidence,
        ledger,
        output,
        {model: (original, ModelConfig("openrouter", model, 60000))},
        uuid.uuid4(),
        "commit",
        run_case,
        {},
    )
    assert len(requests) == before


async def test_session_affinity_dry_run_is_offline_and_part_of_manifest_identity(
    monkeypatch,
    capsys,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("No network in affinity dry-run")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("sys.argv", ["suite", "--dry-run", "--session-affinity"])
    await dialogue_suite.main()
    enabled = json.loads(capsys.readouterr().out)
    disabled = manifest(session_affinity=False)
    assert enabled["execution"]["session_affinity"] == "per-model"
    assert disabled["execution"]["session_affinity"] == "implicit"
    assert enabled != disabled


async def test_session_transport_failure_keeps_header_evidence_without_sdk_retry(tmp_path) -> None:
    from dialogue_affinity import session_id_for_model

    requests: list[httpx.Request] = []

    async def fail(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, json={"error": {"message": "Provider unavailable"}})

    provider = LocalProvider("https://openrouter.ai/api/v1", "test-key")
    await provider.client.close()
    provider.client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(fail)),
        max_retries=2,
    )
    ledger = RequestLedger(tmp_path / "requests.jsonl", budget=1)
    identifier = session_id_for_model("trial", "vendor/a:free")
    trace = SuiteProvider(
        provider,
        ledger,
        key="trial",
        case="fixture",
        model="vendor/a:free",
        run=0,
        commit="commit",
        ceiling=1,
        session_id=identifier,
    )
    try:
        with pytest.raises(InternalServerError):
            await trace.generate("system", [], "vendor/a:free")
    finally:
        await provider.client.close()
    assert len(requests) == ledger.spent == trace.count == 1
    assert provider.client.max_retries == 2
    assert ledger.results()[0].status == "error"
    assert ledger.results()[0].request_headers == {"x-session-id": identifier}
    assert not ledger.interrupted()
