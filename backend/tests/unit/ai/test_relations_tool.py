"""ADR 0023 W1.2/W3 — the DM relation edge tool."""

from app.ai.tools import tools_relation
from app.ai.tools.tools_base import execute_tool
from app.memory.graph_config import GraphConfig


def _world() -> dict:
    return {
        "factions": {
            "the-hollow": {"name": "The Hollow"},
            "thornhaven-council": {"name": "Thornhaven Council"},
        },
        "npcs": {"u1": {"name": "Lyra", "slug": "lyra", "lifecycle": "alive"}},
        "relations": [],
    }


def _run(world: dict, **arguments):
    return execute_tool(
        "update_relation",
        arguments,
        world,
        {},
        baseline={"taxonomy": {}},
        since_turn=3,
        since_game_minutes=600,
    )


def test_creates_edge_with_resolved_endpoints_and_frozen_time():
    result = _run(
        _world(),
        src_type="npc",
        src="Lyra",
        dst_type="player",
        dst="player",
        kind="companion",
        stance=60,
        label="Travels with you",
    )
    assert result.outcome == "succeeded"
    assert result.world_state["relations"] == [
        {
            "src": {"type": "npc", "id": "u1"},
            "dst": {"type": "player", "id": None},
            "kind": "companion",
            "stance": 60,
            "label": "Travels with you",
            "prominent": True,
            "since_turn": 3,
            "since_game_minutes": 600,
        }
    ]


def test_upserts_open_edge_without_duplicating():
    world = _world()
    _run(
        world,
        src_type="faction",
        src="The Hollow",
        dst_type="faction",
        dst="thornhaven-council",
        kind="faction",
        stance=-10,
    )
    _run(
        world,
        src_type="faction",
        src="the-hollow",
        dst_type="faction",
        dst="thornhaven-council",
        kind="faction",
        stance=-50,
        label="open hostility",
    )
    assert len(world["relations"]) == 1
    assert world["relations"][0]["stance"] == -50
    assert world["relations"][0]["label"] == "open hostility"


def test_closed_edge_is_reopened_as_a_new_edge():
    world = _world()
    _run(
        world,
        src_type="faction",
        src="The Hollow",
        dst_type="faction",
        dst="thornhaven-council",
        kind="faction",
        stance=-10,
    )
    world["relations"][0]["until_turn"] = 2
    _run(
        world,
        src_type="faction",
        src="The Hollow",
        dst_type="faction",
        dst="thornhaven-council",
        kind="faction",
        stance=-20,
    )
    assert len(world["relations"]) == 2
    assert world["relations"][1]["since_turn"] == 3
    assert "until_turn" not in world["relations"][1]


def test_unknown_kind_is_rejected_with_candidates():
    result = _run(
        _world(),
        src_type="faction",
        src="The Hollow",
        dst_type="player",
        dst="player",
        kind="bogus",
        stance=1,
    )
    assert result.outcome == "rejected"
    assert "ally" in result.description


def test_tool_description_explains_kinds():
    description = tools_relation.UpdateRelation.tool_description().lower()
    assert "travels with the player" in description
    assert "always visible" in description
    assert "companion (prominent=true)" in description
    assert description.count("ally:") == 1


def test_generation_schema_lists_config_and_world_kinds_once():
    schema = tools_relation.UpdateRelation.to_generation_schema(
        {"relation_kinds": [{"kind": "oath", "prominent": True, "description": "a sacred oath"}]}
    )
    description = schema["function"]["description"]
    assert "oath (prominent=True): a sacred oath" in description
    assert "ally:" in description
    assert description.count("ally:") == 1


def test_cap_allows_updating_an_existing_edge(monkeypatch):
    monkeypatch.setattr(
        tools_relation,
        "get_graph_config",
        lambda: GraphConfig.model_validate(
            {
                "max_relations": 1,
                "prominent_max_relations": 1,
                "scene_max_relations": 1,
                "faction_max_relations": 1,
                "extract_max_per_batch": 1,
            }
        ),
    )
    world = _world()
    arguments = {
        "src_type": "faction",
        "src": "The Hollow",
        "dst_type": "player",
        "dst": "player",
        "kind": "ally",
        "stance": 10,
    }
    assert _run(world, **arguments).outcome == "succeeded"
    result = _run(world, **{**arguments, "stance": 20})
    assert result.outcome == "succeeded"
    assert len(world["relations"]) == 1
    assert world["relations"][0]["stance"] == 20


def test_ambiguous_faction_is_rejected_with_candidates():
    world = _world()
    world["factions"]["other"] = {"name": "The Hollow"}
    result = _run(
        world,
        src_type="faction",
        src="The Hollow",
        dst_type="player",
        dst="player",
        kind="ally",
        stance=1,
    )
    assert result.outcome == "rejected"
    assert "the-hollow" in result.description
