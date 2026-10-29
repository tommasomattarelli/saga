from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.dialogue_markers import RESERVED_START


@dataclass(frozen=True)
class NPCInteraction:
    npc_name: str
    lines: tuple[str, ...]
    action: str | None = None
    axis_changes: dict[str, int] = field(default_factory=dict)
    reveals_secret: bool = False


@dataclass(frozen=True)
class NPCSpeaking(NPCInteraction):
    status: Literal["speaking"] = field(default="speaking", init=False)


@dataclass(frozen=True)
class NPCSilent(NPCInteraction):
    status: Literal["silent"] = field(default="silent", init=False)


@dataclass(frozen=True)
class NPCFailure:
    npc_name: str
    status: Literal["failure"] = field(default="failure", init=False)

    @property
    def note(self) -> str:
        return f"{self.npc_name} did not answer. Continue without inventing their speech."


NPCResult = NPCSpeaking | NPCSilent | NPCFailure


class _ActorResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    status: Literal["speaking", "silent"]
    lines: list[str]
    action: str | None = None
    axis_changes: dict[str, int] = {}
    reveals_secret: bool = False

    @field_validator("axis_changes", mode="before")
    @classmethod
    def _numeric_deltas(cls, raw: object) -> dict[str, int]:
        if not isinstance(raw, dict):
            return {}
        return {
            str(axis): int(delta)
            for axis, delta in raw.items()
            if isinstance(delta, int | float) and not isinstance(delta, bool)
        }


def parse_actor_result(name: str, data: object, max_lines: int) -> NPCResult:
    response = _ActorResponse.model_validate(data)
    if any(RESERVED_START.search(text) for text in [*response.lines, response.action or ""]):
        return NPCFailure(name)
    usable = tuple(line for line in response.lines if line.strip() not in {"", "...", "…"})
    if response.status == "silent":
        if response.lines:
            return NPCFailure(name)
        return NPCSilent(name, (), response.action, response.axis_changes, response.reveals_secret)
    if not usable:
        return NPCFailure(name)
    return NPCSpeaking(
        name, usable[:max_lines], response.action, response.axis_changes, response.reveals_secret
    )
