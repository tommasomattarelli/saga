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


def test_session_identity_is_stable_opaque_and_distinct_for_independent_trials() -> None:
    from dialogue_affinity import session_id_for_trial

    plan = manifest(
        models=["vendor/a:free", "vendor/b:free"],
        case_names=["npc_followup", "actor_en"],
        runs=2,
        session_affinity=True,
    )
    keys = [
        trial_key(plan, case, model, run)
        for case in plan["cases"]
        for model in plan["models"]
        for run in range(2)
    ]
    identifiers = [session_id_for_trial(key) for key in keys]
    assert len(set(identifiers)) == len(keys)
    for key, identifier in zip(keys, identifiers, strict=True):
        assert identifier == session_id_for_trial(key)
        assert str(uuid.UUID(identifier)) == identifier
        assert len(identifier) <= 256
        assert "vendor" not in identifier


async def test_parallel_trial_clients_keep_one_header_for_dm_and_actors_without_mutation(
    provider: tuple[LocalProvider, list[httpx.Request]],
    tmp_path,
) -> None:
    from dialogue_affinity import session_id_for_trial

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
            session_id=session_id_for_trial(key),
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
        assert request.headers["x-session-id"] == session_id_for_trial(key)
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
        session_id_for_trial("trial-a"),
        session_id_for_trial("trial-b"),
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


async def test_runner_reuses_one_session_through_two_turns_and_separates_other_cases(
    provider: tuple[LocalProvider, list[httpx.Request]],
    tmp_path,
) -> None:
    from dialogue_affinity import session_id_for_trial

    original, requests = provider
    model = "vendor/a:free"
    plan = manifest(
        models=[model],
        case_names=["npc_followup", "actor_en", "two_npc_conversation"],
        runs=1,
        session_affinity=True,
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
    assert not interrupted and len(evidence) == 3
    conversation_key = trial_key(plan, "two_npc_conversation", model, 0)
    for key, row in evidence.items():
        assert row["session_id"] == session_id_for_trial(key)
    conversation = [row for row in ledger.results() if row.key.startswith(conversation_key)]
    assert len(conversation) == 2
    assert all(
        row.request_headers["x-session-id"] == session_id_for_trial(conversation_key)
        for row in conversation
    )
    assert len({request.headers["x-session-id"] for request in requests}) == 3


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
    disabled = manifest()
    assert enabled["execution"]["session_affinity"] == "per-trial"
    assert disabled["execution"]["session_affinity"] == "implicit"
    assert enabled != disabled


async def test_session_transport_failure_keeps_header_evidence_without_sdk_retry(tmp_path) -> None:
    from dialogue_affinity import session_id_for_trial

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
    identifier = session_id_for_trial("trial")
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
