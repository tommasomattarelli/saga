import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import openai
from pydantic import BaseModel, JsonValue

from app.ai.providers.local import LocalProvider
from app.ai.providers.usage import capture_usage, usage_scope
from eval.cache.plan import Plan, write_plan
from eval.cache.report import write_report
from eval.support.ledger import Attempt, RequestLedger


class GenerationMetadata(BaseModel):
    data: dict[str, JsonValue]


async def collect_metadata(
    client: openai.AsyncOpenAI, ledger: RequestLedger, directory: Path
) -> None:
    fields = {
        "id",
        "provider_name",
        "provider_responses",
        "session_id",
        "model",
        "created_at",
        "native_tokens_prompt",
        "native_tokens_completion",
        "native_tokens_reasoning",
        "native_tokens_cached",
        "total_cost",
        "cache_discount",
        "upstream_inference_cost",
        "finish_reason",
        "native_finish_reason",
        "latency",
        "generation_time",
        "response_cache_source_id",
    }
    with (directory / "metadata.jsonl").open("a") as handle:
        for attempt in ledger.results():
            generation_id = attempt.response.get("id")
            if not isinstance(generation_id, str):
                continue
            row: dict[str, object] = {"id": generation_id, "at": datetime.now(UTC).isoformat()}
            try:
                response = await client.get(
                    "/generation",
                    cast_to=httpx.Response,
                    options={"params": {"id": generation_id}},
                )
                metadata = GenerationMetadata.model_validate_json(response.text)
                row["data"] = {key: value for key, value in metadata.data.items() if key in fields}
            except (openai.APIError, ValueError):
                row["error"] = "Generation metadata unavailable; inspect the dashboard."
            handle.write(json.dumps(row) + "\n")
            handle.flush()


async def run_block(plan: Plan, provider: LocalProvider, directory: Path, owner: UUID) -> None:
    write_plan(plan, directory)
    try:
        with (directory / "started.json").open("x") as handle:
            json.dump({"owner": str(owner), "started_at": datetime.now(UTC).isoformat()}, handle)
    except FileExistsError:
        raise ValueError(
            "This block already started; inspect its evidence before any new run."
        ) from None
    ledger = RequestLedger(directory / "requests.jsonl", budget=8)
    if ledger.spent:
        raise ValueError("Existing request evidence cannot be reused for another block.")
    client = provider.client.with_options(max_retries=0, timeout=120)
    previous_end: float | None = None
    try:
        for item in plan.requests:
            payload = plan.payloads[item.payload]
            headers = {"x-session-id": item.session_id}
            started = time.monotonic()
            attempt = Attempt(
                key=f"{plan.run_id}|{plan.model}|{plan.phase}|{item.index}",
                scenario=plan.fixture,
                probe=plan.phase,
                run=item.trial,
                checkpoint=plan.run_id,
                model=plan.model,
                commit=plan.commit,
                dirty=plan.dirty,
                request=payload.body(),
                request_headers=headers,
                request_hash=item.request_hash,
                correlation={
                    "regime": item.regime,
                    "step": item.step,
                    "payload": item.payload,
                    "started_at": datetime.now(UTC).isoformat(),
                    "gap_seconds": started - previous_end if previous_end is not None else None,
                },
            )
            ledger.reserve(attempt)
            try:
                # Read SDK usage directly: production rejects length-capped prose, this probe doesn't.
                response = await client.chat.completions.create(
                    model=payload.model,
                    messages=payload.wire_messages(),
                    tools=payload.wire_tools(),
                    tool_choice="auto",
                    max_tokens=payload.max_tokens,
                    extra_headers=headers,
                )
                with usage_scope(role="dm", step=item.step):
                    usage = capture_usage(response, model=plan.model)
                attempt.usage = [asdict(usage)] if usage is not None else []
                raw = response.model_dump(mode="json")
                raw_usage = raw.get("usage") or {}
                prompt_usage = raw_usage.get("prompt_tokens_details") or {}
                choices = raw.get("choices") or []
                attempt.response = {
                    "id": raw.get("id"),
                    "model": raw.get("model"),
                    "provider": raw.get("provider"),
                    "finish_reason": choices[0].get("finish_reason") if choices else None,
                    "cache_write_tokens": prompt_usage.get("cache_write_tokens"),
                    "reported_usage": raw_usage,
                }
                attempt.status = "error" if raw.get("error") or not choices else "ok"
                if attempt.status == "error":
                    attempt.error = "Provider returned an upstream error or no choices."
            except openai.APIError as exc:
                attempt.status = "error"
                status = getattr(exc, "status_code", None)
                attempt.error = f"Provider request failed{f' (HTTP {status})' if status else ''}."
            finally:
                attempt.seconds = time.monotonic() - started
                if attempt.status != "reserved":
                    ledger.record(attempt)
                previous_end = time.monotonic()
            print(
                f"{item.index + 1}/8 {item.regime} trial={item.trial + 1} {item.payload}: {attempt.status}",
                flush=True,
            )
            if attempt.status == "error":
                break
    finally:
        write_report(directory, plan)
    try:
        await collect_metadata(client, ledger, directory)
    finally:
        write_report(directory, plan)
