"""ADR 0019 A1-A2 — the campaign-owned, typed quest registry.

A record's identity is its explicit ``id`` tag, never its display name: two
records may share a title, and lookup is exact. Status is the containing list.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

QUEST_ID_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"
_MAX_ID_LENGTH = 64


def is_valid_quest_id(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= _MAX_ID_LENGTH
        and re.fullmatch(QUEST_ID_PATTERN, value) is not None
    )


class QuestStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class QuestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=_MAX_ID_LENGTH, pattern=QUEST_ID_PATTERN)
    name: str
    description: str = ""
    objectives: list[str] = []

    @field_validator("name")
    @classmethod
    def _display_name_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a quest display name cannot be blank")
        return value


class QuestRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: list[QuestRecord] = []
    completed: list[QuestRecord] = []
    failed: list[QuestRecord] = []
    abandoned: list[QuestRecord] = []

    @model_validator(mode="after")
    def _ids_are_unique_across_lists(self) -> QuestRegistry:
        seen: set[str] = set()
        for status in QuestStatus:
            for quest in getattr(self, status.value):
                if quest.id in seen:
                    raise ValueError(f"duplicate quest id '{quest.id}' across the registry")
                seen.add(quest.id)
        return self

    def find(self, quest_id: str) -> tuple[QuestStatus, QuestRecord] | None:
        for status in QuestStatus:
            for quest in getattr(self, status.value):
                if quest.id == quest_id:
                    return status, quest
        return None
