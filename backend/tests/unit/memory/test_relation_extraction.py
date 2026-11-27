"""ADR 0023 S3 — batch relation extraction contract."""

import json
from uuid import uuid4

import pytest

from app.memory.batch_source_contracts import BatchInput
from app.memory.producer_contracts import FactsPayload, MemoryOutputError, resolve_relations


def _source(*, operations: list[dict] | None = None) -> BatchInput:
    return BatchInput.model_validate_json(
        json.dumps(
            {
                "turns": [
                    {
                        "reference": "t1",
                        "turn_id": str(uuid4()),
                        "player_action": "Ask Mira",
                        "narration": "Mira answers.",
                        "history_depth": 4,
                        "game_minutes": 700,
                        "operations": operations or [],
                    }
                ]
            }
        )
    )


def _payload(kind: str = "companion", src: str = "Mira") -> FactsPayload:
    return FactsPayload.model_validate(
        {
            "facts": [],
            "relations": [
                {
                    "src": {"type": "npc", "name": src},
                    "dst": {"type": "faction", "name": "The Hollow"},
                    "kind": kind,
                    "stance": 40,
                    "label": "Trusted with the key",
                    "source_turns": ["t1"],
                }
            ],
        }
    )


def _npc_operation() -> dict:
    return {
        "id": str(uuid4()),
        "ordinal": 1,
        "step": None,
        "beat": None,
        "payload": {
            "origin": "npc",
            "name": "create_npc",
            "outcome": "succeeded",
            "arguments": {"name": "Mira"},
            "result": {
                "kind": "npc",
                "npc_id": "npc-mira",
                "status": "created",
                "action": None,
                "axis_changes": {},
            },
            "deltas": [],
        },
    }


def test_resolves_endpoints_and_preserves_frozen_clock():
    world = {"factions": {"the-hollow": {"name": "The Hollow"}}}
    resolved = resolve_relations(_payload(), _source(operations=[_npc_operation()]), world, {})
    assert len(resolved) == 1
    assert resolved[0].src.model_dump() == {"type": "npc", "id": "npc-mira"}
    assert resolved[0].dst.model_dump() == {"type": "faction", "id": "the-hollow"}
    assert resolved[0].prominent is True
    assert resolved[0].since_turn == 4
    assert resolved[0].since_game_minutes == 700


def test_tool_written_triple_wins():
    world = {"factions": {"the-hollow": {"name": "The Hollow"}}}
    tool_operation = {
        "id": str(uuid4()),
        "ordinal": 2,
        "step": None,
        "beat": None,
        "payload": {
            "origin": "tool",
            "name": "update_relation",
            "outcome": "succeeded",
            "arguments": {
                "src_type": "npc",
                "src": "Mira",
                "dst_type": "faction",
                "dst": "The Hollow",
                "kind": "companion",
            },
            "result": {"kind": "message", "description": "Relation updated."},
            "deltas": [],
        },
    }
    resolved = resolve_relations(
        _payload(), _source(operations=[_npc_operation(), tool_operation]), world, {}
    )
    assert resolved == ()


def test_unknown_kind_reports_candidates():
    with pytest.raises(MemoryOutputError, match="ally"):
        resolve_relations(_payload(kind="bogus"), _source(), {}, {})
