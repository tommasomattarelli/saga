"""Tests for GameClock model and world state clock functions."""

from app.memory.world_state import GameClock, advance_game_clock, migrate_world_state


class TestGameClock:
    def test_defaults(self):
        clock = GameClock()
        assert clock.total_minutes == 0
        assert clock.current_hour == 0
        assert clock.current_day == 1
        assert clock.time_of_day == "night"
        assert clock.current_season == "spring"

    def test_morning_start(self):
        clock = GameClock(total_minutes=480)  # 8:00 AM
        assert clock.current_hour == 8
        assert clock.current_day == 1
        assert clock.time_of_day == "morning"

    def test_afternoon(self):
        clock = GameClock(total_minutes=780)  # 1:00 PM
        assert clock.current_hour == 13
        assert clock.time_of_day == "afternoon"

    def test_evening(self):
        clock = GameClock(total_minutes=1080)  # 6:00 PM
        assert clock.current_hour == 18
        assert clock.time_of_day == "evening"

    def test_night(self):
        clock = GameClock(total_minutes=1380)  # 11:00 PM
        assert clock.current_hour == 23
        assert clock.time_of_day == "night"

    def test_day_rollover(self):
        clock = GameClock(total_minutes=1440)  # 24h = day 2
        assert clock.current_day == 2
        assert clock.current_hour == 0

    def test_day_calculation(self):
        clock = GameClock(total_minutes=1440 * 3 + 480)  # Day 4, 8:00 AM
        assert clock.current_day == 4
        assert clock.current_hour == 8

    def test_season_spring(self):
        clock = GameClock(total_minutes=1440 * 0)  # Day 1
        assert clock.current_season == "spring"

    def test_season_summer(self):
        clock = GameClock(total_minutes=1440 * 30)  # Day 31
        assert clock.current_season == "summer"

    def test_season_autumn(self):
        clock = GameClock(total_minutes=1440 * 60)  # Day 61
        assert clock.current_season == "autumn"

    def test_season_winter(self):
        clock = GameClock(total_minutes=1440 * 90)  # Day 91
        assert clock.current_season == "winter"

    def test_season_cycles(self):
        clock = GameClock(total_minutes=1440 * 120)  # Day 121 → spring again
        assert clock.current_season == "spring"

    def test_serialization(self):
        clock = GameClock(total_minutes=480)
        data = clock.model_dump()
        assert data["total_minutes"] == 480
        assert data["current_hour"] == 8
        assert data["current_day"] == 1
        assert data["time_of_day"] == "morning"
        assert data["current_season"] == "spring"


class TestAdvanceGameClock:
    def test_basic_advance(self):
        state = {"clock": {"total_minutes": 480}, "meta": {"current_season": "spring"}}
        updated = advance_game_clock(state, 60)
        assert updated["clock"]["total_minutes"] == 540
        assert updated["time_of_day"] == "morning"

    def test_advance_crosses_time_of_day(self):
        state = {"clock": {"total_minutes": 480}, "meta": {"current_season": "spring"}}
        updated = advance_game_clock(state, 240)  # +4 hours → noon
        assert updated["clock"]["total_minutes"] == 720
        assert updated["time_of_day"] == "afternoon"

    def test_advance_no_clock_defaults(self):
        state = {}
        updated = advance_game_clock(state, 60)
        assert updated["clock"]["total_minutes"] == 540  # 480 default + 60

    def test_does_not_mutate_original(self):
        state = {"clock": {"total_minutes": 480}, "meta": {"current_season": "spring"}}
        advance_game_clock(state, 60)
        assert state["clock"]["total_minutes"] == 480


class TestMigrationV1ToV2:
    def test_adds_clock(self):
        v1_state = {
            "meta": {"schema_version": 1, "world_name": "Test", "current_season": "spring"},
            "locations": {},
        }
        migrated = migrate_world_state(v1_state)
        assert migrated["meta"]["schema_version"] == 3
        assert "clock" in migrated
        assert migrated["clock"]["total_minutes"] == 480

    def test_v0_to_v3_full_migration(self):
        v0_state = {"locations": {"town": "visited"}}
        migrated = migrate_world_state(v0_state)
        assert migrated["meta"]["schema_version"] == 3
        assert "clock" in migrated
        assert "npcs" in migrated
        assert "companions" in migrated
        assert "narrative" in migrated

    def test_v3_not_modified(self):
        v3_state = {
            "meta": {"schema_version": 3, "world_name": "Test"},
            "clock": {"total_minutes": 1000},
            "npcs": {},
            "companions": {},
            "narrative": {"event_log": []},
        }
        migrated = migrate_world_state(v3_state)
        assert migrated["clock"]["total_minutes"] == 1000
