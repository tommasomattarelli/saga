from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from app.ai.response_validation import (
    DiagnosticCode,
    validation_diagnostics,
)
from app.ai.tools.dm_tools import get_tool


@dataclass(frozen=True)
class ToolPreflightDiagnostic:
    call_index: int
    code: DiagnosticCode
    path: tuple[str | int, ...]


class ToolPreflightError(ValueError):
    def __init__(self, diagnostics: tuple[ToolPreflightDiagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        super().__init__("Tool response rejected before execution.")


def preflight_tool_calls(calls: list[dict], allowed: set[str]) -> None:
    diagnostics: list[ToolPreflightDiagnostic] = []
    for index, call in enumerate(calls):
        name = call.get("name")
        tool = get_tool(name) if isinstance(name, str) else None
        if tool is None:
            diagnostics.append(
                ToolPreflightDiagnostic(index, DiagnosticCode.TOOL_NOT_REGISTERED, ())
            )
        elif name not in allowed:
            diagnostics.append(ToolPreflightDiagnostic(index, DiagnosticCode.TOOL_UNAVAILABLE, ()))

        arguments = call.get("args")
        if not isinstance(arguments, dict):
            diagnostics.append(ToolPreflightDiagnostic(index, DiagnosticCode.EXPECTED_OBJECT, ()))
            continue
        if tool is None:
            continue
        try:
            encoded = json.dumps(arguments, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            diagnostics.append(ToolPreflightDiagnostic(index, DiagnosticCode.INVALID_JSON, ()))
            continue
        try:
            tool.model_validate_json(encoded, strict=True)
        except ValidationError as error:
            diagnostics.extend(
                ToolPreflightDiagnostic(index, diagnostic.code, diagnostic.path)
                for diagnostic in validation_diagnostics(error, tool.model_json_schema())
            )

    if diagnostics:
        raise ToolPreflightError(tuple(diagnostics))
