from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.memory.batch_source_contracts import BatchInput, NPCSourceResult
from app.memory.document_contracts import (
    CanonicalReference,
    EntityType,
    FactEntity,
    FactImportance,
    FactMetadata,
    NonEmptyText,
    SummaryPayload,
    _DocumentModel,
)
from app.memory.production_policy import FactsPolicy

FactCategory = Literal["event", "information", "commitment", "relationship", "state_change"]
AssertionType = Literal["occurrence", "statement", "belief", "intention"]
TurnReference = Annotated[str, Field(pattern=r"^t[1-9][0-9]*$")]


class MemoryOutputError(ValueError):
    def __init__(self, message: str, diagnostic_path: tuple[str | int, ...] = ()) -> None:
        super().__init__(message)
        self.diagnostic_path = diagnostic_path


class GeneratedEntity(_DocumentModel):
    name: NonEmptyText
    type: EntityType
    role: NonEmptyText

    @field_validator("name", "role")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Entity text must not be blank.")
        return value


class GeneratedFact(_DocumentModel):
    content: NonEmptyText
    category: FactCategory
    assertion_type: AssertionType
    entities: tuple[GeneratedEntity, ...]
    attribution: tuple[Annotated[int, Field(ge=0)], ...]
    source_turns: tuple[TurnReference, ...] = Field(min_length=1)
    temporal_references: tuple[NonEmptyText, ...]
    importance: FactImportance

    @field_validator(
        "entities", "attribution", "source_turns", "temporal_references", mode="before"
    )
    @classmethod
    def freeze_entries(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("content", "temporal_references")
    @classmethod
    def reject_blank(cls, value: str | tuple[str, ...]) -> str | tuple[str, ...]:
        values = (value,) if isinstance(value, str) else value
        if any(not item.strip() for item in values):
            raise ValueError("Fact text must not be blank.")
        return value

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if len(set(self.source_turns)) != len(self.source_turns):
            raise ValueError("Fact sources must be unique.")
        if len(set(self.attribution)) != len(self.attribution) or any(
            index >= len(self.entities) for index in self.attribution
        ):
            raise ValueError("Attribution must reference unique entity indices.")
        if self.assertion_type == "occurrence" and self.attribution:
            raise ValueError("An occurrence has actors, not declarative attribution.")
        if self.assertion_type != "occurrence" and not self.attribution:
            raise ValueError("Statements, beliefs and intentions require attribution.")
        return self


class FactsPayload(_DocumentModel):
    facts: tuple[GeneratedFact, ...]

    @field_validator("facts", mode="before")
    @classmethod
    def freeze_facts(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class BatchPayload(FactsPayload):
    summary: SummaryPayload


class ResolvedFact(_DocumentModel):
    content: NonEmptyText
    category: FactCategory
    assertion_type: AssertionType
    metadata: FactMetadata
    source_turn_ids: tuple[UUID, ...]


def validate_source(source: BatchInput) -> None:
    if len({turn.reference for turn in source.turns}) != len(source.turns) or len(
        {turn.turn_id for turn in source.turns}
    ) != len(source.turns):
        raise MemoryOutputError("Batch source identities and references must be unique.")


def resolve_entities(fact: GeneratedFact, source: BatchInput) -> tuple[FactEntity, ...]:
    candidates: dict[tuple[str, str], set[str]] = defaultdict(set)
    for turn in source.turns:
        if turn.reference not in fact.source_turns:
            continue
        for operation in turn.operations or ():
            payload = operation.payload
            if payload.outcome != "succeeded":
                continue
            if (
                payload.origin == "npc"
                and payload.name in {"create_npc", "invoke_npc"}
                and isinstance(payload.result, NPCSourceResult)
            ):
                name = payload.arguments.get("name")
                if isinstance(name, str) and name.strip():
                    candidates[("npc", name.strip().casefold())].add(payload.result.npc_id)
            if payload.origin == "tool" and payload.name == "update_quest":
                name, quest_id = payload.arguments.get("name"), payload.arguments.get("quest_id")
                if (
                    isinstance(name, str)
                    and name.strip()
                    and isinstance(quest_id, str)
                    and quest_id
                ):
                    candidates[("quest", name.strip().casefold())].add(quest_id)
    entities = []
    for entity in fact.entities:
        ids = candidates[(entity.type, entity.name.strip().casefold())]
        canonical_ref = (
            CanonicalReference(type=entity.type, id=next(iter(ids))) if len(ids) == 1 else None
        )
        entities.append(FactEntity(**entity.model_dump(), canonical_ref=canonical_ref))
    return tuple(entities)


def validate_facts(
    payload: FactsPayload,
    source: BatchInput,
    policy: FactsPolicy,
) -> tuple[ResolvedFact, ...]:
    validate_facts_context(payload, source, policy)
    return resolve_facts(payload, source)


def validate_facts_context(
    payload: FactsPayload,
    source: BatchInput,
    policy: FactsPolicy,
) -> None:
    validate_source(source)
    if len(payload.facts) > policy.max_per_batch:
        raise MemoryOutputError("The generated facts exceed the batch limit.", ("facts",))
    levels = {level.name for level in policy.importance_levels}
    source_references = {turn.reference for turn in source.turns}
    for index, fact in enumerate(payload.facts):
        if not set(fact.source_turns) <= source_references:
            raise MemoryOutputError(
                "A fact references a turn outside its batch.",
                ("facts", index, "source_turns"),
            )
        if fact.importance.level not in levels:
            raise MemoryOutputError(
                "A fact uses an importance level outside the policy.",
                ("facts", index, "importance", "level"),
            )


def resolve_facts(payload: FactsPayload, source: BatchInput) -> tuple[ResolvedFact, ...]:
    turns = {turn.reference: turn.turn_id for turn in source.turns}
    resolved = []
    for fact in payload.facts:
        resolved.append(
            ResolvedFact(
                content=fact.content,
                category=fact.category,
                assertion_type=fact.assertion_type,
                metadata=FactMetadata(
                    entities=resolve_entities(fact, source),
                    attribution=fact.attribution,
                    temporal_references=fact.temporal_references,
                    importance=fact.importance,
                ),
                source_turn_ids=tuple(turns[reference] for reference in fact.source_turns),
            )
        )
    return tuple(resolved)
