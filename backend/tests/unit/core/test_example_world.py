"""ADR 0008 S1 — the shipped example World loads and validates green (C4)."""

from pathlib import Path

from app.core.world_loader import load_world
from app.core.world_validator import validate_world

EXAMPLE_WORLD = Path(__file__).parents[4] / "worlds" / "the-awakening"


def test_example_world_loads_and_validates():
    asset = load_world(EXAMPLE_WORLD)
    assert validate_world(asset, max_depth=8) == []


def test_example_world_exercises_the_full_surface():
    asset = load_world(EXAMPLE_WORLD)
    scales = {asset.taxonomy.kind(n.kind).scale for n in asset.nodes.values()}
    assert scales == {"outdoor", "interior"}
    assert asset.edges, "example world must ship travel edges"
    assert asset.encounters, "example world must ship an encounter table"
    assert asset.factions and asset.npcs
    assert asset.scenario is not None
    assert asset.scenario.opening.start_location in asset.nodes
