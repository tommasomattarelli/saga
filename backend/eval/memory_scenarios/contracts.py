from dataclasses import dataclass

from pydantic import JsonValue

from app.memory.batch_source_contracts import BatchInput


@dataclass(frozen=True)
class BuiltScenario:
    sources: BatchInput
    annotations: dict[str, JsonValue]
    batches: tuple[BatchInput, ...]
    tail: BatchInput | None
    plan: dict[str, JsonValue] | None
