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


def _normalize_world_updates(response: DMResponse) -> DMResponse:
    """Ensure world_updates is always a list of typed dicts or None."""
    wu = response.world_updates
    if wu is None:
        return response
    if isinstance(wu, dict) and "key" in wu:
        # Single typed update → wrap in list
        # Also extract any nested updates the DM may have embedded
        updates: list[dict] = []
        nested_keys = []
        for k, v in wu.items():
            if isinstance(v, dict) and "key" in v:
                updates.append(v)
                nested_keys.append(k)
        clean_parent = {k: v for k, v in wu.items() if k not in nested_keys}
        updates.insert(0, clean_parent)
        response.world_updates = updates
        logger.info(
            "world_updates_normalized", original="dict_with_key", result_count=len(updates)
        )
    return response


def parse_dm_response(raw: str) -> DMResponse:
    """Parse DM raw output into a validated DMResponse.

    Pipeline: strip markdown fences → repair_json → json.loads → DMResponse.model_validate → normalize
    Falls back to treating entire response as narration if all parsing fails.
    """
    stripped = _strip_fences(raw)

    json_match = re.search(r"\{[\s\S]*\}", stripped)
    if not json_match:
        logger.warning("dm_response_no_json_found", raw_length=len(raw), raw_preview=raw[:300])
        return DMResponse(narration=raw.strip())

    json_str = json_match.group()

    try:
        repaired = repair_json(json_str)
        data = json.loads(repaired) if isinstance(repaired, str) else repaired
    except Exception:
        logger.warning(
            "dm_response_json_repair_failed", raw_length=len(raw), raw_preview=raw[:300]
        )
        return DMResponse(narration=raw.strip())

    if not isinstance(data, dict):
        logger.warning("dm_response_not_dict", type=type(data).__name__)
        return DMResponse(narration=raw.strip())

    try:
        response = DMResponse.model_validate(data)
    except Exception as exc:
        logger.warning("dm_response_validation_failed", error=str(exc), raw_preview=raw[:300])
        return DMResponse(narration=data.get("narration", raw.strip()))

    response = _normalize_world_updates(response)

    logger.info(
        "dm_response_parsed",
        has_world_updates=response.world_updates is not None,
        world_updates_type=type(response.world_updates).__name__
        if response.world_updates
        else "none",
        world_updates_count=len(response.world_updates)
        if isinstance(response.world_updates, list)
        else 0,
        has_dice=response.dice_required is not None,
        scene_mood=str(response.scene_mood),
    )
    return response
