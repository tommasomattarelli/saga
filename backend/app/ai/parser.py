"""Parse structured DM output from AI responses with JSON healing."""

from __future__ import annotations

import json
import re

import structlog
from json_repair import repair_json

from app.ai.schemas.dm_response import DMResponse, SceneMood

logger = structlog.get_logger()

# Re-export for backward compatibility
__all__ = ["DMResponse", "SceneMood", "parse_dm_response"]

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```")


def _strip_fences(raw: str) -> str:
    match = _FENCE_RE.search(raw)
    return match.group(1).strip() if match else raw.strip()


def parse_dm_response(raw: str) -> DMResponse:
    """Parse DM raw output into a validated DMResponse.

    Pipeline: strip markdown fences → repair_json → json.loads → DMResponse.model_validate
    Falls back to treating entire response as narration if all parsing fails.
    """
    stripped = _strip_fences(raw)

    json_match = re.search(r"\{[\s\S]*\}", stripped)
    if not json_match:
        logger.warning("dm_response_no_json_found", raw_length=len(raw))
        return DMResponse(narration=raw.strip())

    json_str = json_match.group()

    try:
        repaired = repair_json(json_str)
        data = json.loads(repaired) if isinstance(repaired, str) else repaired
    except Exception:
        logger.warning("dm_response_json_repair_failed", raw_length=len(raw))
        return DMResponse(narration=raw.strip())

    if not isinstance(data, dict):
        logger.warning("dm_response_not_dict", type=type(data).__name__)
        return DMResponse(narration=raw.strip())

    try:
        return DMResponse.model_validate(data)
    except Exception as exc:
        logger.warning("dm_response_validation_failed", error=str(exc))
        return DMResponse(narration=data.get("narration", raw.strip()))
