from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from app.ai.providers.base import AIProvider
from app.ai.router import ModelConfig
from app.memory.producer_prompts import ProducerKind
from eval.dialogue.limits import FreeRequestLimiter
from eval.memory.calls import EvaluationPausedError, execute_attempt, run_global_chain
from eval.memory.plan import MemoryPlan, digest, validate_plan, write_plan
from eval.memory.run_lock import evidence_run_lock
from eval.support.dialogue_affinity import provider_with_session
from eval.support.ledger import RequestLedger


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
    session_ids = {model: plan.model_session_id(model) for model in plan.models}
    for attempt in ledger.results():
        if (
            attempt.model not in session_ids
            or attempt.request_headers.get("x-session-id") != session_ids[attempt.model]
        ):
            raise ValueError("completed request affinity differs from the frozen manifest")
    output_path = directory / "outputs.jsonl"
    generations: dict[str, tuple[AIProvider, ModelConfig]] = {}
    for model in plan.models:
        provider, config = await resolve_eval_generation(
            owner, model, allow_paid=model in plan.paid_models
        )
        if config.max_tokens != plan.output_cap:
            raise ValueError("resolved output cap differs from the frozen manifest")
        provider = provider_with_session(provider, session_ids[model])
        headers = getattr(getattr(provider, "client", None), "default_headers", {})
        if headers.get("x-session-id") != session_ids[model]:
            raise ValueError("resolved provider does not preserve evaluation session affinity")
        generations[model] = (provider, config)
    stop = asyncio.Event()
    limiter = FreeRequestLimiter()

    async def run_model(model: str) -> None:
        provider, config = generations[model]
        session_id = session_ids[model]
        for repetition in range(1, plan.repetitions + 1):
            if stop.is_set():
                return
            for batch_index, source in enumerate(plan.sources):
                modes: tuple[tuple[str, ProducerKind], ...] = (
                    ("unified", "batch"),
                    ("split-summary", "summary"),
                    ("split-facts", "facts"),
                )
                for mode, kind in modes:
                    if stop.is_set():
                        return
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
                    await execute_attempt(
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
                        session_id=session_id,
                        limiter=limiter,
                        stop=stop,
                    )
                    if stop.is_set():
                        return
            if plan.global_policy is not None:
                await run_global_chain(
                    plan,
                    model,
                    repetition,
                    provider,
                    config,
                    ledger,
                    output_path,
                    prepare_request,
                    session_id,
                    limiter,
                    stop,
                )
                if stop.is_set():
                    return

    async def guarded_model(model: str) -> None:
        try:
            await run_model(model)
        except Exception:
            stop.set()
            raise

    outcomes = await asyncio.gather(
        *(guarded_model(model) for model in plan.models), return_exceptions=True
    )
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome
    if stop.is_set():
        raise EvaluationPausedError(
            "Provider failure recorded; check authorization, policy and quota before a new evidence run."
        )
