"""ADR 0008 S3 — <scene> location block: spine-only + travel options (J1/J4)."""

from pathlib import Path

import pytest

from app.ai.prompts.scene import render_location_block
from app.core.world_access import WorldView
from app.core.world_instantiation import instantiate_world
from app.core.world_loader import load_world

EXAMPLE_WORLD = Path(__file__).parents[4] / "worlds" / "the-awakening"


@pytest.fixture
def world():
    baseline, state, _ = instantiate_world(load_world(EXAMPLE_WORLD))
    return baseline, state


def render_at(baseline, state, slug):
    state["player_position"] = baseline["slug_map"][slug]
    view = WorldView(baseline, state)
    return "\n".join(render_location_block(view, state["player_position"]))


def test_outdoor_node_shows_spine_and_travel_options(world):
    baseline, state = world
    block = render_at(baseline, state, "thornhaven")
    assert 'name="Thornhaven"' in block
    assert "The Verdant Reach" in block  # breadcrumb spine
    assert "<travel_options>" in block
    assert "Old Mines" in block
    assert "min" in block
    assert "<places_inside>" in block
    assert "The Gilded Tankard" in block


def test_interior_node_shows_exits_and_outside(world):
    baseline, state = world
    block = render_at(baseline, state, "common-room")
    assert "<exits>" in block
    assert "Cellar" in block
    assert "<outside>The Gilded Tankard</outside>" in block
    assert "<travel_options>" not in block


def test_status_rendered_when_present(world):
    baseline, state = world
    thorn_id = baseline["slug_map"]["thornhaven"]
    state["node_status"][thorn_id] = {
        "status": "in fiamme",
        "description": "Il mercato brucia.",
        "duration_minutes": None,
        "applied_at": 480,
        "modifiers": {},
    }
    block = render_at(baseline, state, "thornhaven")
    assert "in fiamme" in block


def test_block_respects_token_cap(world):
    baseline, state = world
    thorn_id = baseline["slug_map"]["thornhaven"]
    baseline["nodes"][thorn_id]["description"] = "x" * 100_000
    block = render_at(baseline, state, "thornhaven")
    assert len(block) <= 700 * 4 + len("  </location>") + 1
    assert block.rstrip().endswith("</location>")
