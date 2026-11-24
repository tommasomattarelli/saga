from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NonEmptyText = Annotated[str, Field(min_length=1)]
EntityType = Literal["player", "npc", "faction", "location", "item", "quest", "other"]


class _DocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SummaryPayload(_DocumentModel):
    text: NonEmptyText

    @field_validator("text")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be empty or whitespace")
        return value


class GlobalPayload(_DocumentModel):
    story_so_far: NonEmptyText
    open_threads: tuple[NonEmptyText, ...]
    relationships: tuple[NonEmptyText, ...]
    resolved_threads: tuple[NonEmptyText, ...]

    @field_validator("story_so_far", "open_threads", "relationships", "resolved_threads")
    @classmethod
    def reject_whitespace_only(cls, value: str | tuple[str, ...]) -> str | tuple[str, ...]:
        values = (value,) if isinstance(value, str) else value
        if any(not item.strip() for item in values):
            raise ValueError("text must not be empty or whitespace")
        return value

    @field_validator("open_threads", "relationships", "resolved_threads", mode="before")
    @classmethod
    def freeze_entries(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class CanonicalReference(_DocumentModel):
    type: EntityType
    id: NonEmptyText

    @field_validator("id")
    @classmethod
    def reject_whitespace_only_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("id must not be empty or whitespace")
        return value


class FactEntity(_DocumentModel):
    name: NonEmptyText
    type: EntityType
    role: NonEmptyText
    canonical_ref: CanonicalReference | None = None

    @field_validator("name", "role")
    @classmethod
    def reject_whitespace_only_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be empty or whitespace")
        return value


class FactImportance(_DocumentModel):
    level: NonEmptyText
    reason: NonEmptyText

    @field_validator("level", "reason")
    @classmethod
    def reject_whitespace_only_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be empty or whitespace")
        return value


class FactMetadata(_DocumentModel):
    entities: tuple[FactEntity, ...]
    attribution: tuple[Annotated[int, Field(ge=0)], ...]
    temporal_references: tuple[NonEmptyText, ...]
    importance: FactImportance

    @field_validator("entities", "attribution", "temporal_references", mode="before")
    @classmethod
    def freeze_entries(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("temporal_references")
    @classmethod
    def reject_whitespace_only_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not reference.strip() for reference in value):
            raise ValueError("temporal references must not be empty or whitespace")
        return value

    @model_validator(mode="after")
    def validate_attribution(self) -> Self:
        if len(self.attribution) != len(set(self.attribution)):
            raise ValueError("attribution indices must be unique")
        if any(index >= len(self.entities) for index in self.attribution):
            raise ValueError("attribution index must refer to an entity")
        return self
