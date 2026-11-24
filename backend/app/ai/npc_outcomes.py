import json
from collections.abc import Collection
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt

from app.ai.response_contracts import ResponseContract
from app.ai.response_validation import (
    DiagnosticCode,
    ResponseValidationError,
    ValidationDiagnostic,
    validate_response,
)
from app.core.dialogue_markers import RESERVED_START
from app.core.psychology import DEFAULT_PSYCHOLOGY
from app.models.psychology import PsychologyDef


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


class NPCResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    status: Literal["speaking", "silent"]
    lines: list[str]
    action: str | None = None
    axis_changes: dict[str, StrictInt] = Field(default_factory=dict)
    reveals_secret: bool = False


NPC_RESPONSE_CONTRACT = ResponseContract("npc_actor", "v1", NPCResponse)


def npc_response_schema(psychology: PsychologyDef | None = None) -> dict[str, JsonValue]:
    schema = deepcopy(NPC_RESPONSE_CONTRACT.schema)
    properties = cast(dict[str, JsonValue], schema["properties"])
    axis_changes = cast(dict[str, JsonValue], properties["axis_changes"])
    delta_schema = axis_changes["additionalProperties"]
    axis_changes["properties"] = {
        name: deepcopy(delta_schema) for name in (psychology or DEFAULT_PSYCHOLOGY).axes
    }
    axis_changes["required"] = []
    axis_changes["additionalProperties"] = False
    return schema


def parse_actor_result(
    name: str,
    data: object,
    max_lines: int,
    psychology: PsychologyDef | None = None,
) -> NPCResult:
    raw = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    response = validate_response(raw, NPC_RESPONSE_CONTRACT).model
    validate_actor_response(response, max_lines, psychology)
    return actor_result_from_response(name, response)


def validate_actor_response(
    response: NPCResponse,
    max_lines: int,
    psychology: PsychologyDef | None = None,
    axis_names: Collection[str] | None = None,
) -> None:
    pdef = psychology or DEFAULT_PSYCHOLOGY
    allowed_axes = pdef.axes if axis_names is None else axis_names
    invalid: list[ValidationDiagnostic] = []
    if len(response.lines) > max_lines:
        invalid.append(ValidationDiagnostic(DiagnosticCode.ABOVE_MAXIMUM_LENGTH, ("lines",)))
    invalid.extend(
        ValidationDiagnostic(DiagnosticCode.VALIDATION_FAILED, ("lines", index))
        for index, line in enumerate(response.lines)
        if not line.strip() or line.strip() in {"...", "…"}
    )
    if response.status == "speaking" and not response.lines:
        invalid.append(ValidationDiagnostic(DiagnosticCode.MISSING, ("lines",)))
    if response.status == "silent" and response.lines:
        invalid.append(ValidationDiagnostic(DiagnosticCode.VALIDATION_FAILED, ("lines",)))
    if any(axis not in allowed_axes for axis in response.axis_changes):
        invalid.append(ValidationDiagnostic(DiagnosticCode.INVALID_ENUM, ("axis_changes",)))
    if any(RESERVED_START.search(text) for text in [*response.lines, response.action or ""]):
        invalid.append(ValidationDiagnostic(DiagnosticCode.VALIDATION_FAILED, ()))
    if invalid:
        raise ResponseValidationError(tuple(invalid))


def actor_result_from_response(name: str, response: NPCResponse) -> NPCResult:
    if response.status == "silent":
        return NPCSilent(name, (), response.action, response.axis_changes, response.reveals_secret)
    return NPCSpeaking(
        name,
        tuple(response.lines),
        response.action,
        response.axis_changes,
        response.reveals_secret,
    )
