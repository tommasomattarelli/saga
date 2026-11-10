from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.router import get_instance_default
from app.memory.batch_source_contracts import BatchInput
from app.memory.producer_prompts import (
    OUTPUT_MODELS,
    PRODUCER_VERSION,
    ProducerKind,
    prepare_request,
)
from app.memory.production_policy import FactsPolicy, GlobalPolicy


def digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class MemoryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal[1] = 1
    harness_version: str = "1"
    producer_version: str
    implementation_fingerprint: str
    output_cap: int = Field(gt=0)
    sources: tuple[BatchInput, ...]
    source_hashes: tuple[str, ...]
    facts_policy: FactsPolicy
    global_policy: GlobalPolicy | None
    language: str = Field(min_length=1)
    models: tuple[str, ...] = Field(min_length=1)
    repetitions: int = Field(gt=0)
    global_count: int = Field(ge=0)
    paid_models: tuple[str, ...]
    input_sizes: tuple[PreparedInputSize, ...]
    seal: str

    @property
    def call_budget(self) -> int:
        return len(self.models) * self.repetitions * (3 * len(self.sources) + self.global_count)


class PreparedInputSize(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    model: str
    batch: int
    role: ProducerKind
    system_characters: int
    system_utf8_bytes: int
    user_characters: int
    user_utf8_bytes: int
    request_utf8_bytes: int
    note: str


def prepare_plan(
    *,
    sources: list[dict[str, object]],
    facts_policy: dict[str, object],
    global_policy: dict[str, object] | None,
    language: str,
    models: list[str],
    repetitions: int,
    global_count: int,
    paid_models: list[str] | None = None,
) -> MemoryPlan:
    parsed_sources = tuple(
        BatchInput.model_validate_json(json.dumps(source)) for source in sources
    )
    parsed_facts = FactsPolicy.model_validate(facts_policy)
    parsed_global = (
        GlobalPolicy.model_validate(global_policy) if global_policy is not None else None
    )
    if (
        not parsed_sources
        or not language.strip()
        or not models
        or any(not model.strip() for model in models)
    ):
        raise ValueError("sources, language, and models must be explicitly nonempty")
    if global_count and parsed_global is None:
        raise ValueError("global_policy is required when global_count is nonzero")
    if not 0 <= global_count <= len(parsed_sources):
        raise ValueError("global_count cannot exceed available batches")
    if len(set(models)) != len(models):
        raise ValueError("models must be unique")
    selected_paid_models = tuple(paid_models or ())
    if len(set(selected_paid_models)) != len(selected_paid_models) or not set(
        selected_paid_models
    ) <= set(models):
        raise ValueError("paid model allowlist must be unique and selected in models")
    if global_count:
        used_turn_ids: set[str] = set()
        for source in parsed_sources[:global_count]:
            turn_ids = {str(turn.turn_id) for turn in source.turns}
            if used_turn_ids & turn_ids:
                raise ValueError("global source batches must contain distinct turns")
            used_turn_ids.update(turn_ids)
    if repetitions <= 0:
        raise ValueError("repetitions must be positive")
    root = Path(__file__).resolve().parents[2]
    implementation_fingerprint = current_implementation_fingerprint(root)
    input_sizes = _prepared_input_sizes(
        parsed_sources,
        parsed_facts,
        parsed_global,
        language,
        models,
        get_instance_default().max_tokens,
        global_count,
    )
    unsigned = MemoryPlan(
        producer_version=PRODUCER_VERSION,
        implementation_fingerprint=implementation_fingerprint,
        output_cap=get_instance_default().max_tokens,
        sources=parsed_sources,
        source_hashes=tuple(digest(source.model_dump(mode="json")) for source in parsed_sources),
        facts_policy=parsed_facts,
        global_policy=parsed_global,
        language=language,
        models=tuple(models),
        repetitions=repetitions,
        global_count=global_count,
        paid_models=selected_paid_models,
        input_sizes=input_sizes,
        seal="",
    )
    return unsigned.model_copy(update={"seal": plan_seal(unsigned)})


def current_implementation_fingerprint(root: Path | None = None) -> str:
    root = root or Path(__file__).resolve().parents[2]
    files = (
        "pyproject.toml",
        "uv.lock",
        "app/ai/router.py",
        "app/ai/generation_context.py",
        "app/ai/providers/base.py",
        "app/ai/providers/local.py",
        "app/ai/providers/openai.py",
        "app/ai/providers/openai_compat.py",
        "app/ai/providers/usage.py",
        "app/ai/prompts/loader.py",
        "app/ai/prompts/templates/memory_production.yaml",
        "app/ai/prompts/templates/memory_summary.yaml",
        "app/ai/prompts/templates/memory_facts.yaml",
        "app/ai/prompts/templates/memory_global.yaml",
        "app/memory/batch_source_contracts.py",
        "app/memory/document_contracts.py",
        "app/memory/producer_contracts.py",
        "app/memory/producer_entities.py",
        "app/memory/producer_examples.py",
        "app/memory/producer_prompts.py",
        "app/memory/producers.py",
        "app/memory/production_policy.py",
        "eval/support/live_calls.py",
        "eval/support/provider_trace.py",
        "eval/support/ledger.py",
    )
    contents = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
    contents.update(
        {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root / "eval" / "memory").glob("*.py"))
        }
    )
    schemas = {kind: model.model_json_schema() for kind, model in OUTPUT_MODELS.items()}
    return digest({"files": contents, "schemas": schemas, "producer_version": PRODUCER_VERSION})


def plan_seal(plan: MemoryPlan) -> str:
    return digest(plan.model_dump(mode="json", exclude={"seal"}))


def _prepared_input_sizes(
    sources: tuple[BatchInput, ...],
    facts_policy: FactsPolicy,
    global_policy: GlobalPolicy | None,
    language: str,
    models: list[str],
    output_cap: int,
    global_count: int,
) -> tuple[PreparedInputSize, ...]:
    sizes: list[PreparedInputSize] = []
    for model in models:
        for index, source in enumerate(sources):
            kinds: list[ProducerKind] = ["batch", "summary", "facts"]
            if index < global_count:
                kinds.append("global")
            for kind in kinds:
                request = prepare_request(
                    kind,
                    source,
                    language=language,
                    facts_policy=facts_policy,
                    global_policy=global_policy if kind == "global" else None,
                    previous=None,
                )
                provider_request = {
                    "system_prompt": request.system_prompt,
                    "messages": [{"role": "user", "content": request.user_prompt}],
                    "model": model,
                    "max_tokens": output_cap,
                    "json_mode": True,
                }
                encoded = json.dumps(
                    provider_request,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
                sizes.append(
                    PreparedInputSize(
                        model=model,
                        batch=index + 1,
                        role=kind,
                        system_characters=len(request.system_prompt),
                        system_utf8_bytes=len(request.system_prompt.encode("utf-8")),
                        user_characters=len(request.user_prompt),
                        user_utf8_bytes=len(request.user_prompt.encode("utf-8")),
                        request_utf8_bytes=len(encoded),
                        note=(
                            "initial only; successor input unknown until produced"
                            if kind == "global"
                            else ""
                        ),
                    )
                )
    return tuple(sizes)


def validate_plan(plan: MemoryPlan) -> None:
    if plan.seal != plan_seal(plan):
        raise ValueError("manifest seal mismatch; evidence was edited")
    if plan.implementation_fingerprint != current_implementation_fingerprint():
        raise ValueError(
            "producer code, schema, or instructions changed; use a new evidence directory"
        )
    if plan.output_cap != get_instance_default().max_tokens:
        raise ValueError("configured output cap changed; use a new evidence directory")


def write_plan(plan: MemoryPlan, directory: Path) -> None:
    validate_plan(plan)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "manifest.json"
    if path.exists():
        if MemoryPlan.model_validate_json(path.read_text(encoding="utf-8")) != plan:
            raise ValueError("manifest changed; use a new evidence directory")
        return
    with path.open("x", encoding="utf-8") as handle:
        handle.write(plan.model_dump_json(indent=2) + "\n")


def load_plan(directory: Path) -> MemoryPlan:
    plan = load_saved_plan(directory)
    validate_plan(plan)
    return plan


def load_saved_plan(directory: Path) -> MemoryPlan:
    plan = MemoryPlan.model_validate_json(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    if plan.seal != plan_seal(plan):
        raise ValueError("manifest seal mismatch; evidence was edited")
    expected = tuple(digest(source.model_dump(mode="json")) for source in plan.sources)
    if expected != plan.source_hashes:
        raise ValueError("manifest source hash mismatch")
    return plan
