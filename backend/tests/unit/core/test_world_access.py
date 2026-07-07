"""ADR 0008 S3 — WorldView: single merge accessor over baseline + overlay (C11)."""

from pathlib import Path

import pytest

from app.core.world_access import WorldView
from app.core.world_instantiation import instantiate_world
from app.core.world_loader import load_world

EXAMPLE_WORLD = Path(__file__).parents[4] / "worlds" / "the-awakening"


@pytest.fixture(scope="module")
def instantiated():
    return instantiate_world(load_world(EXAMPLE_WORLD))


@pytest.fixture
def view(instantiated):
    import copy

    baseline, state, _ = copy.deepcopy(instantiated)
    return WorldView(baseline, state), baseline, state


class TestNodeAccess:
    def test_node_by_slug_and_uuid(self, view):
        v, baseline, _ = view
        shrine_id = baseline["slug_map"]["shrine-of-first-light"]
        assert v.node(shrine_id)["name"] == "Shrine of First Light"
        assert v.id_of("shrine-of-first-light") == shrine_id

    def test_breadcrumb_names_root_to_node(self, view):
        v, baseline, _ = view
        hall_id = baseline["slug_map"]["common-room"]
        crumbs = v.breadcrumb(hall_id)
        assert crumbs == [
            "The Awakening",
            "The Verdant Reach",
            "Thornhaven",
            "The Gilded Tankard",
            "Common Room",
        ]

    def test_player_position(self, view):
        v, baseline, _ = view
        assert v.player_position() == baseline["slug_map"]["shrine-of-first-light"]


class TestStatusOverlay:
    def test_status_modifiers_apply_to_params(self, view):
        v, baseline, state = view
        thorn_id = baseline["slug_map"]["thornhaven"]
        state["node_status"][thorn_id] = {
            "status": "plague",
            "description": "A sickness spreads.",
            "duration_minutes": None,
            "applied_at": 480,
            "modifiers": {"population": -40},
        }
        node = v.node(thorn_id)
        assert node["params"]["population"] == 200  # 240 - 40
        assert node["status"]["status"] == "plague"

    def test_no_status_means_baseline_untouched(self, view):
        v, baseline, _ = view
        thorn_id = baseline["slug_map"]["thornhaven"]
        assert v.node(thorn_id)["params"]["population"] == 240
        assert v.node(thorn_id)["status"] is None


class TestResolve:
    def test_unique_name_resolves(self, view):
        v, baseline, _ = view
        result = v.resolve("Old Mines")
        assert result.match == baseline["slug_map"]["old-mines"]
        assert result.candidates == []

    def test_slug_resolves(self, view):
        v, baseline, _ = view
        assert v.resolve("old-mines").match == baseline["slug_map"]["old-mines"]

    def test_unknown_returns_no_match(self, view):
        v, _, _ = view
        result = v.resolve("Atlantis")
        assert result.match is None
        assert result.candidates == []

    def test_ambiguous_prefers_scope_near_current(self, instantiated):
        baseline, state, _ = instantiated
        import copy

        baseline = copy.deepcopy(baseline)
        state = copy.deepcopy(state)
        # Forge a second node named "Cellar" far away (under the shrine — global scope),
        # while the original cellar is inside the tavern near the player.
        shrine_id = baseline["slug_map"]["shrine-of-first-light"]
        cellar_id = baseline["slug_map"]["cellar"]
        fake_id = "00000000-0000-0000-0000-000000000001"
        baseline["nodes"][fake_id] = {
            **baseline["nodes"][cellar_id],
            "slug": "far-cellar",
            "parent": shrine_id,
            "children": [],
        }
        baseline["nodes"][shrine_id]["children"].append(fake_id)
        baseline["alias"].setdefault("cellar", []).append(fake_id)
        baseline["slug_map"]["far-cellar"] = fake_id

        # Player inside the tavern's common room → the tavern cellar wins
        state["player_position"] = baseline["slug_map"]["common-room"]
        v = WorldView(baseline, state)
        assert v.resolve("Cellar").match == cellar_id

    def test_equidistant_ambiguity_returns_candidates(self, instantiated):
        baseline, state, _ = instantiated
        import copy

        baseline = copy.deepcopy(baseline)
        state = copy.deepcopy(state)
        thorn_id = baseline["slug_map"]["thornhaven"]
        cellar_id = baseline["slug_map"]["cellar"]
        fake_id = "00000000-0000-0000-0000-000000000002"
        # Second "Cellar" directly under Thornhaven — same distance from the shrine
        baseline["nodes"][fake_id] = {
            **baseline["nodes"][cellar_id],
            "slug": "other-cellar",
            "parent": thorn_id,
            "children": [],
        }
        baseline["nodes"][thorn_id]["children"].append(fake_id)
        baseline["alias"].setdefault("cellar", []).append(fake_id)

        state["player_position"] = baseline["slug_map"]["shrine-of-first-light"]
        v = WorldView(baseline, state)
        result = v.resolve("Cellar")
        assert result.match is None
        assert set(result.candidates) == {cellar_id, fake_id}
