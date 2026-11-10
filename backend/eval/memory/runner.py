from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict
from uuid import UUID

from app.ai.generation_context import generation_context
from app.ai.providers.base import AIProvider
from app.ai.router import ModelConfig
from app.memory.document_contracts import GlobalPayload
from app.memory.producer_contracts import MemoryOutputError
from app.memory.producer_prompts import PreparedMemoryRequest, ProducerKind
from app.memory.producers import MemoryGeneration
from eval.memory.plan import MemoryPlan, digest, validate_plan, write_plan
from eval.memory.run_lock import evidence_run_lock
from eval.support.ledger import Attempt, RequestLedger
from eval.support.provider_trace import ProviderTrace


class EvidenceRow(TypedDict):
    key: str
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
) -> Attempt:
    return Attempt(
        key,
        f"batch-{batch_index + 1}",
        mode,
        repetition,
        model=config.model,
        request=_provider_request(request, config),
        request_hash=digest(_provider_request(request, config)),
        correlation={
            "provider": config.provider,
            "model": config.model,
            "kind": kind,
            "source_hash": request.source_hash,
            "instruction_hash": request.instruction_hash,
        },
    )


async def _execute_attempt(
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
) -> tuple[EvidenceRow, MemoryGeneration | None]:
    from app.memory.producers import generate_memory

    attempt = _new_attempt(key, batch_index, mode, repetition, request, config, kind)
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
        raise EvaluationPausedError(
            "Provider failure recorded; check authorization, policy and quota before a new evidence run."
        )
    return row, generated


async def run_plan(plan: MemoryPlan, directory: Path, owner: UUID, *, authorized: bool) -> None:
    if not authorized:
        raise ValueError("live memory evaluation requires explicit authorization")
    validate_plan(plan)
    directory.mkdir(parents=True, exist_ok=True)
    with evidence_run_lock(directory):
        manifest = directory / "manifest.json"
        if not manifest.exists() and any(
            (directory / name).exists() for name in ("requests.jsonl", "outputs.jsonl")
        ):
            raise ValueError("existing evidence without a manifest requires manual review")
        write_plan(plan, directory)
        await _run_locked(plan, directory, owner)


async def _run_locked(plan: MemoryPlan, directory: Path, owner: UUID) -> None:
    from app.memory.producer_prompts import prepare_request
    from eval.support.live_calls import resolve_eval_generation

    ledger = RequestLedger(directory / "requests.jsonl", budget=plan.call_budget)
    if ledger.interrupted():
        raise ValueError(
            "interrupted requests require manual review; use a new evidence directory"
        )
    if any(attempt.correlation.get("fatal_provider_error") for attempt in ledger.results()):
        raise EvaluationPausedError(
            "A prior provider failure requires intervention and a new evidence directory."
        )
    output_path = directory / "outputs.jsonl"
    for model in plan.models:
        generation = await resolve_eval_generation(
            owner, model, allow_paid=model in plan.paid_models
        )
        provider, config = generation
        if config.max_tokens != plan.output_cap:
            raise ValueError("resolved output cap differs from the frozen manifest")
        for repetition in range(1, plan.repetitions + 1):
            for batch_index, source in enumerate(plan.sources):
                modes: tuple[tuple[str, ProducerKind], ...] = (
                    ("unified", "batch"),
                    ("split-summary", "summary"),
                    ("split-facts", "facts"),
                )
                for mode, kind in modes:
                    key = digest(
                        [model, repetition, batch_index, mode, plan.source_hashes[batch_index]]
                    )
                    if ledger.completed(key):
                        continue
                    request = prepare_request(
                        kind,
                        source,
                        language=plan.language,
                        facts_policy=plan.facts_policy,
                    )
                    await _execute_attempt(
                        ledger=ledger,
                        output_path=output_path,
                        key=key,
                        batch_index=batch_index,
                        mode=mode,
                        kind=kind,
                        repetition=repetition,
                        model=model,
                        request=request,
                        provider=provider,
                        config=config,
                    )
            if plan.global_policy is not None:
                await _run_global_chain(
                    plan, model, repetition, provider, config, ledger, output_path, prepare_request
                )


async def _run_global_chain(
    plan: MemoryPlan,
    model: str,
    repetition: int,
    provider: AIProvider,
    config: ModelConfig,
    ledger: RequestLedger,
    output_path: Path,
    prepare_request: Callable[..., PreparedMemoryRequest],
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
        row, generated = await _execute_attempt(
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
        )
        if row["status"] != "ok" or generated is None:
            break
        global_payload = GlobalPayload.model_validate(generated.payload.model_dump())
