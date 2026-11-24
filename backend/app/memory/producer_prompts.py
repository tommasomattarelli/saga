from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal, cast

from pydantic import BaseModel, JsonValue, ValidationError

from app.ai.prompts.loader import template
from app.ai.response_contracts import ResponseContract
from app.memory.batch_source_contracts import BatchInput
from app.memory.document_contracts import GlobalPayload, SummaryPayload
from app.memory.producer_contracts import (
    BatchPayload,
    FactsPayload,
    MemoryOutputError,
    validate_facts,
    validate_source,
)
from app.memory.producer_examples import worked_example
from app.memory.production_policy import FactsPolicy, GlobalPolicy

ProducerKind = Literal["batch", "summary", "facts", "global"]
MemoryPayload = BatchPayload | FactsPayload | SummaryPayload | GlobalPayload
PRODUCER_VERSION = "memory-v1"
OUTPUT_MODELS: dict[ProducerKind, type[BaseModel]] = {
    "batch": BatchPayload,
    "summary": SummaryPayload,
    "facts": FactsPayload,
    "global": GlobalPayload,
}


@lru_cache
def response_contract(kind: ProducerKind) -> ResponseContract[BaseModel]:
    return ResponseContract(
        name=f"memory-{kind}", version=PRODUCER_VERSION, model_type=OUTPUT_MODELS[kind]
    )


def canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _effective_schema(kind: ProducerKind, facts_policy: FactsPolicy) -> dict[str, JsonValue]:
    schema = response_contract(kind).schema
    if kind in {"batch", "facts"}:
        properties = cast(dict[str, dict[str, JsonValue]], schema["properties"])
        facts = cast(dict[str, JsonValue], properties["facts"])
        facts["maxItems"] = facts_policy.max_per_batch
        definitions = cast(dict[str, dict[str, JsonValue]], schema["$defs"])
        importance = cast(dict[str, JsonValue], definitions["FactImportance"])
        importance_properties = cast(dict[str, dict[str, JsonValue]], importance["properties"])
        level_schema = cast(dict[str, JsonValue], importance_properties["level"])
        level_schema["enum"] = [level.name for level in facts_policy.importance_levels]
    return schema


@dataclass(frozen=True)
class PreparedMemoryRequest:
    kind: ProducerKind
    system_prompt: str
    user_prompt: str
    source: BatchInput
    facts_policy: FactsPolicy
    source_hash: str
    instruction_hash: str
    executor_system_prompt: str = field(default="", repr=False)
    _response_schema_json: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        schema = _effective_schema(self.kind, self.facts_policy)
        object.__setattr__(
            self,
            "_response_schema_json",
            canonical(schema),
        )
        if not self.executor_system_prompt:
            object.__setattr__(
                self,
                "executor_system_prompt",
                _executor_system_prompt(self.system_prompt, schema),
            )

    @property
    def response_schema(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._response_schema_json))

    def validate_output(self, raw: str) -> MemoryPayload:
        try:
            payload = response_contract(self.kind).validate(raw)
            if isinstance(payload, FactsPayload):
                validate_facts(payload, self.source, self.facts_policy)
        except (ValueError, ValidationError) as exc:
            raise MemoryOutputError(
                "The generated memory does not match its source contract."
            ) from exc
        assert isinstance(payload, (BatchPayload, FactsPayload, SummaryPayload, GlobalPayload))
        return payload


def prepare_request(
    kind: ProducerKind,
    source: BatchInput,
    *,
    language: str,
    facts_policy: FactsPolicy,
    global_policy: GlobalPolicy | None = None,
    previous: GlobalPayload | None = None,
) -> PreparedMemoryRequest:
    validate_source(source)
    if kind not in OUTPUT_MODELS:
        raise ValueError("Unknown memory producer.")
    if not language.strip():
        raise ValueError("A campaign language is required.")
    if kind == "global" and global_policy is None:
        raise ValueError("A global target policy is required.")
    if kind != "global" and (previous is not None or global_policy is not None):
        raise ValueError("Only global generation accepts a predecessor or target policy.")
    schema = _effective_schema(kind, facts_policy)
    sections = [template("memory_production", "system")]
    if kind in {"batch", "summary"}:
        sections.append(template("memory_summary", "instructions"))
    if kind in {"batch", "facts"}:
        sections.append(template("memory_facts", "instructions"))
    if kind == "global":
        sections.append(template("memory_global", "instructions"))
    sections.append(template("memory_production", "example"))
    if kind in {"batch", "facts"}:
        sections.append(template("memory_facts", "example"))
    sections.append(worked_example(kind, facts_policy))
    settings = {
        "language": language,
        "facts_policy": facts_policy.model_dump(mode="json"),
        "global_policy": global_policy.model_dump(mode="json") if global_policy else None,
    }
    sections.append(canonical(settings))
    executor_system_prompt = "\n\n".join(
        [*sections, template("memory_production", "executor_output")]
    )
    system_prompt = "\n\n".join(
        [*sections, template("memory_production", "output"), canonical(schema)]
    )
    evidence: dict[str, object] = {"source": source.model_dump(mode="json")}
    if kind == "global":
        evidence["previous"] = previous.model_dump(mode="json") if previous else None
    return PreparedMemoryRequest(
        kind=kind,
        source=source,
        facts_policy=facts_policy,
        system_prompt=system_prompt,
        executor_system_prompt=executor_system_prompt,
        user_prompt=canonical({**settings, **evidence}),
        source_hash=digest(canonical(evidence)) if kind == "global" else source.source_hash(),
        instruction_hash=digest(PRODUCER_VERSION + "\n" + system_prompt),
    )


def _executor_system_prompt(legacy_prompt: str, schema: dict[str, JsonValue]) -> str:
    suffix = "\n\n" + canonical(schema)
    prompt_without_schema = (
        legacy_prompt[: -len(suffix)] if legacy_prompt.endswith(suffix) else legacy_prompt
    )
    return prompt_without_schema.replace(
        template("memory_production", "output"),
        template("memory_production", "executor_output"),
        1,
    )
