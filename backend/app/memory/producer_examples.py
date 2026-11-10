from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.ai.prompts.loader import template
from app.memory.batch_source_contracts import BatchInput
from app.memory.document_contracts import FactImportance, GlobalPayload, SummaryPayload
from app.memory.producer_contracts import (
    BatchPayload,
    FactsPayload,
    validate_facts,
    validate_source,
)
from app.memory.production_policy import FactsPolicy

if TYPE_CHECKING:
    from app.memory.producer_prompts import ProducerKind


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload(kind: ProducerKind, raw: str, facts_policy: FactsPolicy) -> BaseModel:
    if kind == "summary":
        return SummaryPayload.model_validate_json(raw)
    if kind == "global":
        return GlobalPayload.model_validate_json(raw)

    authored = FactsPayload.model_validate_json(raw)
    selected = tuple(
        fact.model_copy(
            update={
                "importance": FactImportance(
                    level=facts_policy.importance_levels[0].name,
                    reason=fact.importance.reason,
                )
            }
        )
        for fact in authored.facts[: facts_policy.max_per_batch]
    )
    payload = (
        BatchPayload(
            summary=SummaryPayload.model_validate_json(
                template("memory_summary", "example_output")
            ),
            facts=selected,
        )
        if kind == "batch"
        else FactsPayload(facts=selected)
    )
    validate_facts(payload, _source(kind), facts_policy)
    return payload


def _source(kind: ProducerKind) -> BatchInput:
    name = "memory_global" if kind == "global" else "memory_production"
    return BatchInput.model_validate_json(template(name, "example_source"))


def worked_example(kind: ProducerKind, facts_policy: FactsPolicy) -> str:
    source_name = "memory_global" if kind == "global" else "memory_production"
    source = _source(kind)
    validate_source(source)
    output_name = {
        "batch": "memory_facts",
        "summary": "memory_summary",
        "facts": "memory_facts",
        "global": "memory_global",
    }[kind]
    payload = _payload(kind, template(output_name, "example_output"), facts_policy)
    bundle: dict[str, object] = {
        "source": source.model_dump(mode="json"),
        "output": payload.model_dump(mode="json"),
    }
    if kind == "global":
        previous = GlobalPayload.model_validate_json(template(source_name, "previous"))
        bundle["previous"] = previous.model_dump(mode="json")
    return f"<worked_example>{_json(bundle)}</worked_example>"
