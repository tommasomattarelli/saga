"""ADR 0008 S3 — travel engine: graph, Naismith time, validation, encounters (F8/F11-F13)."""

from pathlib import Path

import pytest

from app.core.travel import TravelConfig, attempt_move
from app.core.world_access import WorldView
from app.core.world_instantiation import instantiate_world
from app.core.world_loader import load_world

EXAMPLE_WORLD = Path(__file__).parents[4] / "worlds" / "the-awakening"

CONFIG = TravelConfig(elevation_coeff=7.92, local_move_minutes=5)


@pytest.fixture
def world():
    baseline, state, _ = instantiate_world(load_world(EXAMPLE_WORLD))
    return baseline, state


def move(baseline, state, target, rng=None):
    view = WorldView(baseline, state)
    return attempt_move(view, target, CONFIG, rng=rng)


class TestResolution:
    def test_unknown_place_rejected(self, world):
        baseline, state = world
        outcome = move(baseline, state, "Atlantis")
        assert not outcome.ok
        assert "unknown" in outcome.reason.lower()

    def test_already_there_rejected(self, world):
        baseline, state = world
        outcome = move(baseline, state, "Shrine of First Light")
        assert not outcome.ok
        assert "already" in outcome.reason.lower()


class TestTravel:
    def test_authored_edge_travel_advances_clock(self, world):
        baseline, state = world
        outcome = move(baseline, state, "Thornhaven")
        assert outcome.ok
        assert outcome.destination == baseline["slug_map"]["thornhaven"]
        # forest-path: 2 units * 1 km/unit = 2 km, forest x1.5, foot 4 km/h
        # → 2/(4/1.5) = 0.75 h = 45 min
        assert outcome.minutes == 45

    def test_no_route_rejected(self, world):
        baseline, state = world
        # Old Mines is reachable only through Thornhaven; remove that edge
        del baseline["edges"]["north-road"]
        state["player_position"] = baseline["slug_map"]["thornhaven"]
        state["meta"]["current_location"] = state["player_position"]
        outcome = move(baseline, state, "Old Mines")
        assert not outcome.ok
        assert "no route" in outcome.reason.lower()

    def test_edge_override_removes_route(self, world):
        baseline, state = world
        state["edge_overrides"].append({"op": "remove", "edge": "forest-path"})
        outcome = move(baseline, state, "Thornhaven")
        assert not outcome.ok

    def test_authored_travel_time_wins(self, world):
        baseline, state = world
        baseline["edges"]["forest-path"]["travel_time"] = 2.0  # hours
        outcome = move(baseline, state, "Thornhaven")
        assert outcome.ok
        assert outcome.minutes == 120

    def test_multi_hop_path_sums_time(self, world):
        baseline, state = world
        outcome = move(baseline, state, "Old Mines")  # shrine → thornhaven → mines
        assert outcome.ok
        assert outcome.minutes > 45


class TestInteriorMoves:
    def test_enter_building_is_local_move(self, world):
        baseline, state = world
        state["player_position"] = baseline["slug_map"]["thornhaven"]
        state["meta"]["current_location"] = state["player_position"]
        outcome = move(baseline, state, "The Gilded Tankard")
        assert outcome.ok
        assert outcome.minutes == CONFIG.local_move_minutes
        assert outcome.local

    def test_room_to_room_via_exits(self, world):
        baseline, state = world
        state["player_position"] = baseline["slug_map"]["common-room"]
        outcome = move(baseline, state, "Cellar")
        assert outcome.ok
        assert outcome.local

    def test_exit_outside_reaches_parent_site(self, world):
        baseline, state = world
        state["player_position"] = baseline["slug_map"]["common-room"]
        outcome = move(baseline, state, "Thornhaven")
        assert outcome.ok
        assert outcome.destination == baseline["slug_map"]["thornhaven"]


class TestEncounters:
    class AlwaysHit:
        def random(self):
            return 0.0  # always below encounter_chance

        def randint(self, a, b):
            return b  # roll max → last entry

    class NeverHit:
        def random(self):
            return 1.0

        def randint(self, a, b):
            return a

    def _to_mines(self, baseline, state, rng):
        state["player_position"] = baseline["slug_map"]["thornhaven"]
        state["meta"]["current_location"] = state["player_position"]
        return move(baseline, state, "Old Mines", rng=rng)

    def test_no_encounter_when_roll_misses(self, world):
        baseline, state = world
        outcome = self._to_mines(baseline, state, self.NeverHit())
        assert outcome.ok and outcome.encounter is None

    def test_encounter_reported_and_once_consumed(self, world):
        baseline, state = world
        outcome = self._to_mines(baseline, state, self.AlwaysHit())
        assert outcome.encounter is not None
        # 2d8 rolled at max = 16 → the once:true wayshrine entry
        assert "wayshrine" in outcome.encounter["description"]
        assert outcome.encounter["type"] == "event"
        assert "north-road" in outcome.consumed_key

    def test_consumed_once_entry_does_not_refire(self, world):
        baseline, state = world
        first = self._to_mines(baseline, state, self.AlwaysHit())
        state["consumed_encounters"] = {first.consumed_key: [first.encounter["index"]]}
        state["player_position"] = baseline["slug_map"]["thornhaven"]
        second = self._to_mines(baseline, state, self.AlwaysHit())
        # max roll hits the consumed once-entry → falls back to no encounter
        assert second.encounter is None
