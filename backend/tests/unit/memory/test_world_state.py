from app.memory.world_state import (
    merge_world_state,
    migrate_world_state,
    validate_world_state,
)


def test_migrate_v0_to_latest():
    v0_state = {"locations": {"town": "visited"}}
    migrated = migrate_world_state(v0_state)

    assert "meta" in migrated
    assert migrated["meta"]["schema_version"] == 5
    assert migrated["meta"]["world_name"] == "Unknown Land"
    assert migrated["meta"]["current_season"] == "spring"
    assert migrated["locations"]["town"] == "visited"
    assert "clock" in migrated
    assert "combat_state" in migrated
    assert migrated["combat_state"]["active"] is False
    assert "destino_lives" in migrated


def test_migrate_v3_to_v4():
    v3_state = {
        "meta": {"schema_version": 3, "world_name": "Test"},
        "locations": {"town": "visited"},
        "clock": {"total_minutes": 480},
        "npcs": {},
        "companions": {},
        "narrative": {"event_log": []},
    }
    migrated = migrate_world_state(v3_state)
    assert migrated["meta"]["schema_version"] == 5
    assert migrated["locations"]["town"] == "visited"
    assert migrated["combat_state"]["active"] is False
    assert migrated["destino_lives"] == 3
    assert migrated is not v3_state


def test_migrate_up_to_date():
    v4_state = {
        "meta": {"schema_version": 5, "world_name": "Test"},
        "locations": {"town": "visited"},
        "clock": {"total_minutes": 480},
        "npcs": {},
        "companions": {},
        "narrative": {"event_log": []},
        "combat_state": {
            "active": False,
            "round": 0,
            "initiative_order": [],
            "current_turn_index": 0,
        },
        "destino_lives": 3,
    }
    migrated = migrate_world_state(v4_state)
    assert migrated["meta"]["schema_version"] == 5
    assert migrated["locations"]["town"] == "visited"
    assert migrated is not v4_state


def test_validate_world_state():
    state = {
        "meta": {},
        "locations": {},
        "invalid_key": "should be stripped",
        "another_invalid": 123,
    }
    validated = validate_world_state(state)
    assert "meta" in validated
    assert "locations" in validated
    assert "invalid_key" not in validated
    assert "another_invalid" not in validated


def test_merge_world_state():
    current = {
        "meta": {"schema_version": 1},
        "locations": {"town": {"visited": True, "status": "safe"}},
        "factions": {"guards": 50},
    }

    updates = {
        "locations": {"town": {"status": "under_attack"}, "forest": {"visited": False}},
        "factions": {"thieves": 10},
        "invalid_key": "should be dropped",
    }

    merged = merge_world_state(current, updates)

    assert merged["meta"]["schema_version"] == 1
    assert merged["locations"]["town"]["visited"] is True  # preserved
    assert merged["locations"]["town"]["status"] == "under_attack"  # updated
    assert merged["locations"]["forest"]["visited"] is False  # added
    assert merged["factions"]["guards"] == 50  # preserved
    assert merged["factions"]["thieves"] == 10  # added
    assert "invalid_key" not in merged


def test_advance_clock_expires_timed_node_statuses():
    from app.memory.world_state import advance_game_clock

    state = {
        "clock": {"total_minutes": 480},
        "node_status": {
            "node-a": {"status": "fire", "duration_minutes": 60, "applied_at": 480},
            "node-b": {"status": "plague", "duration_minutes": None, "applied_at": 480},
        },
    }
    advanced = advance_game_clock(state, 59)
    assert "node-a" in advanced["node_status"]
    advanced = advance_game_clock(state, 60)
    assert "node-a" not in advanced["node_status"]
    assert "node-b" in advanced["node_status"]  # permanent until lifted
