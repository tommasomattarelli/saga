from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, JsonValue, ValidationError

from app.ai.prompts.loader import template
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


def canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Invalid JSON constant.")


@dataclass(frozen=True)
class PreparedMemoryRequest:
    kind: ProducerKind
    system_prompt: str
    user_prompt: str
    source: BatchInput
    facts_policy: FactsPolicy
    source_hash: str
    instruction_hash: str

    def validate_output(self, raw: str) -> MemoryPayload:
        try:
            data = json.loads(
                raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant
            )
            payload = OUTPUT_MODELS[self.kind].model_validate(data)
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
    schema = OUTPUT_MODELS[kind].model_json_schema()
    if kind in {"batch", "facts"}:
        schema["properties"]["facts"]["maxItems"] = facts_policy.max_per_batch
        schema["$defs"]["FactImportance"]["properties"]["level"]["enum"] = [
            level.name for level in facts_policy.importance_levels
        ]
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
    sections.extend(
        [canonical(settings), template("memory_production", "output"), canonical(schema)]
    )
    system_prompt = "\n\n".join(sections)
    evidence: dict[str, object] = {"source": source.model_dump(mode="json")}
    if kind == "global":
        evidence["previous"] = previous.model_dump(mode="json") if previous else None
    return PreparedMemoryRequest(
        kind=kind,
        source=source,
        facts_policy=facts_policy,
        system_prompt=system_prompt,
        user_prompt=canonical({**settings, **evidence}),
        source_hash=digest(canonical(evidence)) if kind == "global" else source.source_hash(),
        instruction_hash=digest(PRODUCER_VERSION + "\n" + system_prompt),
    )
