from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict

from app.ai.generation_context import generation_context
from app.ai.providers.base import AIProvider
from app.ai.router import ModelConfig
from app.memory.document_contracts import GlobalPayload
from app.memory.producer_contracts import MemoryOutputError
from app.memory.producer_prompts import PreparedMemoryRequest, ProducerKind
from app.memory.producers import MemoryGeneration
from eval.dialogue.limits import FreeRequestLimiter
from eval.memory.plan import MemoryPlan, digest
from eval.support.ledger import Attempt, RequestLedger
from eval.support.provider_trace import ProviderTrace


class EvidenceRow(TypedDict):
    key: str
    session_id: str
    model: str
    repetition: int
    batch: int
    mode: str
    status: str
    provider: str
    seconds: float
    usage: list[dict[str, object]]
    raw: str
    payload: dict[str, object] | None
    facts: list[dict[str, object]]
    error: str


class EvaluationPausedError(RuntimeError):
    pass


def _provider_request(request: PreparedMemoryRequest, config: ModelConfig) -> dict[str, object]:
    return {
        "system_prompt": request.system_prompt,
        "messages": [{"role": "user", "content": request.user_prompt}],
        "model": config.model,
        "max_tokens": config.max_tokens,
        "json_mode": True,
    }


def _new_attempt(
    key: str,
    batch_index: int,
    mode: str,
    repetition: int,
    request: PreparedMemoryRequest,
    config: ModelConfig,
    kind: ProducerKind,
    session_id: str,
) -> Attempt:
    provider_request = _provider_request(request, config)
    headers = {"x-session-id": session_id}
    return Attempt(
        key,
        f"batch-{batch_index + 1}",
        mode,
        repetition,
        model=config.model,
        request=provider_request,
        request_hash=digest({"request": provider_request, "headers": headers}),
        request_headers=headers,
        correlation={
            "provider": config.provider,
            "model": config.model,
            "kind": kind,
            "source_hash": request.source_hash,
            "instruction_hash": request.instruction_hash,
        },
    )


async def execute_attempt(
    *,
    ledger: RequestLedger,
    output_path: Path,
    key: str,
    batch_index: int,
    mode: str,
    kind: ProducerKind,
    repetition: int,
    model: str,
    request: PreparedMemoryRequest,
    provider: AIProvider,
    config: ModelConfig,
    session_id: str,
    limiter: FreeRequestLimiter,
    stop: asyncio.Event,
) -> tuple[EvidenceRow, MemoryGeneration | None]:
    from app.memory.producers import generate_memory

    wait = await limiter.wait(model)
    if stop.is_set():
        return (
            {
                "key": key,
                "session_id": session_id,
                "model": model,
                "repetition": repetition,
                "batch": batch_index + 1,
                "mode": mode,
                "status": "stopped",
                "provider": config.provider,
                "seconds": 0.0,
                "usage": [],
                "raw": "",
                "payload": None,
                "facts": [],
                "error": "",
            },
            None,
        )
    attempt = _new_attempt(key, batch_index, mode, repetition, request, config, kind, session_id)
    attempt.rate_limit_wait_seconds = wait
    ledger.reserve(attempt)
    trace = ProviderTrace(provider, role=f"memory_{kind}")
    started = time.monotonic()
    generated: MemoryGeneration | None = None
    raw = ""
    error = ""
    fatal_provider_error = False
    try:
        with generation_context((trace, config)):
            generated = await generate_memory(request)
        raw = generated.raw
        attempt.status = "ok"
    except MemoryOutputError:
        raw = str(trace.response.get("text", ""))
        attempt.status = "error"
        attempt.error = "Generated output failed memory contract validation."
        error = attempt.error
    except Exception:
        raw = str(trace.response.get("text", ""))
        attempt.status = "error"
        attempt.error = "Provider call failed; evaluation paused to protect quota."
        attempt.correlation["fatal_provider_error"] = True
        error = attempt.error
        fatal_provider_error = True
    seconds = time.monotonic() - started
    usage = [asdict(item) for item in trace.usage]
    attempt.seconds = seconds
    attempt.usage = usage
    attempt.response = {
        "raw": raw,
        "payload": generated.payload.model_dump(mode="json") if generated else {},
        "facts": [fact.model_dump(mode="json") for fact in generated.facts] if generated else [],
    }
    payload = generated.payload.model_dump(mode="json") if generated else None
    facts = [fact.model_dump(mode="json") for fact in generated.facts] if generated else []
    row: EvidenceRow = {
        "key": key,
        "session_id": session_id,
        "model": model,
        "repetition": repetition,
        "batch": batch_index + 1,
        "mode": mode,
        "status": attempt.status,
        "provider": config.provider,
        "seconds": seconds,
        "usage": usage,
        "raw": raw,
        "payload": payload,
        "facts": facts,
        "error": error,
    }
    ledger.record(attempt)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    if fatal_provider_error:
        stop.set()
    return row, generated


async def run_global_chain(
    plan: MemoryPlan,
    model: str,
    repetition: int,
    provider: AIProvider,
    config: ModelConfig,
    ledger: RequestLedger,
    output_path: Path,
    prepare_request: Callable[..., PreparedMemoryRequest],
    session_id: str,
    limiter: FreeRequestLimiter,
    stop: asyncio.Event,
) -> None:
    global_payload: GlobalPayload | None = None
    for batch_index, source in enumerate(plan.sources[: plan.global_count]):
        key = digest([model, repetition, "global", batch_index, plan.source_hashes[batch_index]])
        if ledger.completed(key):
            prior = next((item for item in ledger.results() if item.key == key), None)
            if prior is None or prior.status != "ok":
                break
            saved_payload = prior.response.get("payload")
            if not isinstance(saved_payload, dict) or not saved_payload:
                break
            try:
                global_payload = GlobalPayload.model_validate(saved_payload)
            except ValueError:
                break
            continue
        request = prepare_request(
            "global",
            source,
            language=plan.language,
            facts_policy=plan.facts_policy,
            global_policy=plan.global_policy,
            previous=global_payload,
        )
        row, generated = await execute_attempt(
            ledger=ledger,
            output_path=output_path,
            key=key,
            batch_index=batch_index,
            mode="global",
            kind="global",
            repetition=repetition,
            model=model,
            request=request,
            provider=provider,
            config=config,
            session_id=session_id,
            limiter=limiter,
            stop=stop,
        )
        if row["status"] != "ok" or generated is None:
            break
        global_payload = GlobalPayload.model_validate(generated.payload.model_dump())
