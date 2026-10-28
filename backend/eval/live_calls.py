import copy
import hashlib
import json
import subprocess
import time
import uuid
from dataclasses import replace

import httpx
import openai
from actor_probe import actor_request, run_actor
from ledger import Attempt, RequestLedger
from probes import PROBES_BY_NAME, grade
from provider_trace import ProviderTrace
from scenario import Scenario

from app.ai.generation_context import Generation, generation_context
from app.ai.prompts.dm import build_dm_system_prompt
from app.ai.providers.local import LocalProvider
from app.ai.router import ModelConfig, get_user_generation
from app.ai.tools.dm_tools import get_tool_schemas
from app.ai.tools.tool_groups import resolve_active_tools_from_state
from app.core.npc_resolver import npcs_at_current_location
from app.exceptions import AIProviderError


class EvaluationPausedError(RuntimeError):
    pass


async def validate_free_models(models: list[str]) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
    catalog = {model["id"]: model for model in response.json()["data"]}
    for model_id in models:
        model = catalog.get(model_id)
        if (
            not model
            or not model_id.endswith(":free")
            or "tools" not in model.get("supported_parameters", [])
            or any(
                float(model.get("pricing", {}).get(key, -1)) != 0
                for key in ("prompt", "completion")
            )
        ):
            raise ValueError(f"Selected free tool-capable model is unavailable: {model_id}")


async def resolve_eval_generation(user_id: uuid.UUID, model: str) -> Generation:
    provider, config = await get_user_generation(user_id)
    if config.provider != "openrouter" or not model.endswith(":free"):
        raise ValueError(
            "Live evaluation requires the owner's OpenRouter profile and a selected free model."
        )
    if isinstance(provider, LocalProvider):
        provider = copy.copy(provider)
        # The shared personal client stays untouched; SDK retries must not hide requests.
        provider.client = provider.client.with_options(max_retries=0)
    return provider, replace(config, model=model)


def source_identity() -> tuple[str, bool]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--", ".", ":!../scratch"], text=True
    )
    return commit, bool(status.strip())


def dm_request(sc: Scenario, probe: str, config: ModelConfig) -> dict:
    allowed = resolve_active_tools_from_state(sc.campaign.world_state)
    return {
        "system_prompt": build_dm_system_prompt(
            sc.campaign,
            summary_context=sc.summary_context,
            global_summary=sc.global_summary,
            recalled_memories=sc.recalled_memories(probe),
            allowed_tools=allowed,
        ),  # type: ignore[arg-type]
        "messages": sc.messages(probe),
        "tools": get_tool_schemas(allowed),
        "model": config.model,
        "max_tokens": config.max_tokens,
    }


async def run_trial(
    generation: Generation,
    sc: Scenario,
    probe: str,
    run: int,
    ledger: RequestLedger,
    *,
    checkpoint: str,
) -> Attempt | None:
    provider, config = generation
    actor = probe == "actor_language"
    if actor and (
        "npc_speaks" not in sc.stimuli or not npcs_at_current_location(sc.campaign.world_state)
    ):
        return None
    request = actor_request(sc, config) if actor else dm_request(sc, probe, config)
    commit, dirty = source_identity()
    digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    key = f"{checkpoint}|{config.model}|{sc.name}|{probe}|{run}|{commit}|{digest}"
    if ledger.completed(key):
        return None
    attempt = Attempt(
        key,
        sc.name,
        probe,
        run,
        checkpoint=checkpoint,
        model=config.model,
        commit=commit,
        dirty=dirty,
        request=request,
    )
    ledger.reserve(attempt)
    trace = ProviderTrace(provider)
    started = time.monotonic()
    try:
        if actor:
            with generation_context((trace, config)):
                public, attempt.failed = await run_actor(sc)
            attempt.response = {"raw": trace.response, "actor": public}
        else:
            response = await trace.generate_with_tools(**request)
            attempt.response = trace.response
            attempt.failed = grade(
                PROBES_BY_NAME[probe],
                response.text or "",
                {call.name for call in response.tool_calls},
                expect_language=sc.language,
            )
    except Exception as exc:
        trace.error = exc
    attempt.request = trace.request or request
    attempt.seconds = time.monotonic() - started
    attempt.status = "error" if trace.error else "ok"
    if trace.error:
        status = getattr(trace.error, "status_code", None)
        attempt.error = f"Provider request failed{f' (HTTP {status})' if status else ''}."
        attempt.failed = ["transport-or-capability-error"]
    ledger.record(attempt)
    in_band_limit = isinstance(trace.error, AIProviderError) and "(code 429)" in str(trace.error)
    if isinstance(trace.error, openai.RateLimitError) or in_band_limit:
        raise EvaluationPausedError("Provider quota/rate limit reached; checkpoint saved.")
    return attempt
