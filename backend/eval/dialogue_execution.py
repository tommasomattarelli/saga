import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from dialogue_affinity import session_id_for_trial
from dialogue_cases import CASES, scenario_for
from dialogue_evidence import append_evidence
from dialogue_limits import FreeRequestLimiter, TrialBudget
from dialogue_plan import trial_key
from dialogue_requests import SuiteProvider
from dialogue_runtime import evaluation_dispatch
from ledger import RequestLedger
from scenario import Scenario

from app.ai.generation_context import Generation
from app.ai.router import ModelConfig

type CaseRunner = Callable[
    [str, Scenario, SuiteProvider, ModelConfig, uuid.UUID], Awaitable[tuple[dict, list[str]]]
]


def trial_result(trace: SuiteProvider, data: dict, failed: list[str]) -> dict:
    if trace.errors:
        failed.append("provider-error")
    if trace.exhausted:
        failed.append("evaluation-request-cap")
    return {
        "event": "result",
        "requests": trace.count,
        "data": data,
        "observed_checks": [] if trace.exhausted or trace.paused else sorted(set(failed)),
        "trial_status": (
            "request_budget_stopped"
            if trace.exhausted
            else "provider_paused"
            if trace.paused
            else "provider_error"
            if trace.errors
            else "evaluation_error"
            if "foreground-run-incomplete" in failed
            else "model_result"
        ),
        "provider_error": trace.errors,
        "request_cap_reached": trace.exhausted,
        "retryable": bool({"foreground-run-incomplete", "provider-error"} & set(failed))
        and not trace.exhausted,
    }


async def run_models(
    plan: dict,
    completed: dict[str, dict],
    ledger: RequestLedger,
    results: Path,
    generations: dict[str, Generation],
    owner: uuid.UUID,
    commit: str,
    run_case: CaseRunner,
    timing: dict,
) -> None:
    budget = TrialBudget(ledger)
    limiter = FreeRequestLimiter()
    stop = asyncio.Event()
    model_seconds: dict[str, float] = {}

    async def worker(model: str) -> None:
        started = time.monotonic()
        try:
            for run in range(plan["runs_per_model_case"]):
                for case in (next(c for c in CASES if c.name == name) for name in plan["cases"]):
                    if stop.is_set():
                        return
                    key = trial_key(plan, case.name, model, run)
                    recorded = completed.get(key)
                    unstarted = (
                        recorded is not None
                        and recorded.get("requests") == 0
                        and recorded.get("trial_status") == "request_budget_stopped"
                    )
                    if recorded is not None and not recorded.get("retryable") and not unstarted:
                        continue
                    provider, config = generations[model]
                    trace = SuiteProvider(
                        provider,
                        ledger,
                        key=key,
                        case=case.name,
                        model=model,
                        run=run,
                        commit=commit,
                        ceiling=case.ceiling,
                        checkpoint=plan["suite"],
                        limiter=limiter,
                        stop=stop,
                        session_id=(
                            session_id_for_trial(key)
                            if plan.get("execution", {}).get("session_affinity") == "per-trial"
                            else None
                        ),
                    )
                    async with budget.hold(
                        case.ceiling, lambda trace=trace: trace.count
                    ) as admitted:
                        if stop.is_set():
                            return
                        row = {
                            "event": "started",
                            "key": key,
                            "case": case.name,
                            "model": model,
                            "run": run,
                            "commit": commit,
                            "source_hash": plan["source_hash"],
                            "ledger": str(ledger.path.resolve()),
                            "session_id": trace.request_headers.get("x-session-id"),
                        }
                        if not admitted:
                            row.update(
                                event="result",
                                requests=0,
                                data={},
                                trial_status="request_budget_stopped",
                                observed_checks=[],
                                retryable=False,
                            )
                            append_evidence(results, row)
                            completed[key] = row
                            return
                        append_evidence(results, row)
                        trial_started = time.monotonic()
                        try:
                            data, failed = await run_case(
                                case.name, scenario_for(case.name), trace, config, owner
                            )
                        except Exception:
                            data, failed = {}, ["foreground-run-incomplete"]
                        row.update(trial_result(trace, data, failed))
                        row["seconds"] = time.monotonic() - trial_started
                        append_evidence(results, row)
                        completed[key] = row
                        print(
                            f"Recorded {case.name}/{model}/{run}: {trace.count} requests.",
                            flush=True,
                        )
        finally:
            model_seconds[model] = time.monotonic() - started

    started = time.monotonic()
    try:
        with evaluation_dispatch():
            async with asyncio.TaskGroup() as tasks:
                for model in plan["models"]:
                    tasks.create_task(worker(model), name=f"eval:{model}")
    finally:
        timing.update(wall_seconds=time.monotonic() - started, model_wall_seconds=model_seconds)
    if stop.is_set():
        print("Provider quota/rate limit: saved evidence; stopping without retry.")
