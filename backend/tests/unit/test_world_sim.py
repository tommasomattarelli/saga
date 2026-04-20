"""Unit tests for app/core/world_sim.py."""

from __future__ import annotations

import pytest

from app.core.world_sim import WorldEvent, simulate_world_tick


class TestWorldEvent:
    def test_defaults(self):
        ev = WorldEvent(description="Something happened")
        assert ev.description == "Something happened"
        assert ev.faction is None
        assert ev.location is None
        assert ev.impact == "minor"

    def test_custom_fields(self):
        ev = WorldEvent(
            description="Battle",
            faction="The Empire",
            location="Fortress",
            impact="major",
        )
        assert ev.faction == "The Empire"
        assert ev.location == "Fortress"
        assert ev.impact == "major"


class TestSimulateWorldTick:
    @pytest.mark.asyncio
    async def test_advances_hour(self):
        world_state: dict = {"time": {"hour": 10}}
        await simulate_world_tick(world_state, turn_number=1, player_location="town")
        assert world_state["time"]["hour"] == 11

    @pytest.mark.asyncio
    async def test_wraps_hour_at_midnight(self):
        world_state: dict = {"time": {"hour": 23}}
        await simulate_world_tick(world_state, turn_number=1, player_location="town")
        assert world_state["time"]["hour"] == 0

    @pytest.mark.asyncio
    async def test_creates_time_key_if_missing(self):
        world_state: dict = {}
        await simulate_world_tick(world_state, turn_number=1, player_location="town")
        assert "time" in world_state
        assert "hour" in world_state["time"]

    @pytest.mark.asyncio
    async def test_no_faction_events_on_non_multiple_of_5(self):
        world_state = {
            "factions": {"The Guild": {"active_plan": "takeover"}}
        }
        events = await simulate_world_tick(world_state, turn_number=3, player_location="town")
        assert events == []

    @pytest.mark.asyncio
    async def test_faction_event_on_multiple_of_5(self):
        world_state = {
            "factions": {"The Guild": {"active_plan": "takeover"}}
        }
        events = await simulate_world_tick(world_state, turn_number=5, player_location="town")
        assert len(events) == 1
        assert isinstance(events[0], WorldEvent)
        assert events[0].faction == "The Guild"
        assert events[0].impact == "moderate"

    @pytest.mark.asyncio
    async def test_no_faction_event_when_no_active_plan(self):
        world_state = {
            "factions": {"The Guild": {"active_plan": None}}
        }
        events = await simulate_world_tick(world_state, turn_number=5, player_location="town")
        assert events == []

    @pytest.mark.asyncio
    async def test_multiple_factions_with_active_plans(self):
        world_state = {
            "factions": {
                "Faction A": {"active_plan": "scheme"},
                "Faction B": {"active_plan": None},
                "Faction C": {"active_plan": "attack"},
            }
        }
        events = await simulate_world_tick(world_state, turn_number=10, player_location="town")
        faction_names = {e.faction for e in events}
        assert "Faction A" in faction_names
        assert "Faction C" in faction_names
        assert "Faction B" not in faction_names

    @pytest.mark.asyncio
    async def test_empty_world_state(self):
        world_state: dict = {}
        events = await simulate_world_tick(world_state, turn_number=5, player_location="town")
        assert events == []
