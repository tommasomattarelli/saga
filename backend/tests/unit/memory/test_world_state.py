from app.memory.world_state import (
    CURRENT_SCHEMA_VERSION,
    merge_world_state,
    migrate_world_state,
    validate_world_state,
)


def test_migrate_v0_to_latest():
    v0_state = {"locations": {"town": "visited"}}
    migrated = migrate_world_state(v0_state)

    assert "meta" in migrated
    assert migrated["meta"]["schema_version"] == CURRENT_SCHEMA_VERSION
    assert migrated["meta"]["world_name"] == "Unknown Land"
    assert migrated["meta"]["current_season"] == "spring"
    assert migrated["locations"]["town"] == "visited"
    assert "clock" in migrated
    assert "fate_interventions_left" in migrated
    # v4 adds combat_state, v8 takes it back out: combat is not a mode (ADR 0003 B1).
    assert "combat_state" not in migrated


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
    assert migrated["meta"]["schema_version"] == CURRENT_SCHEMA_VERSION
    assert migrated["locations"]["town"] == "visited"
    assert "combat_state" not in migrated
    assert migrated["fate_interventions_left"] == 3
    assert migrated is not v3_state


def test_migrate_v5_to_v6_seeds_psychology():
    # ADR 0005 C2: trivial rung — no scalar lift, defaults + met_player only.
    v5_state = {
        "meta": {"schema_version": 5, "world_name": "Test"},
        "npcs": {"Bran": {"name": "Bran", "disposition_toward_player": 40}},
    }
    migrated = migrate_world_state(v5_state)
    bran = next(n for n in migrated["npcs"].values() if n["name"] == "Bran")
    assert migrated["meta"]["schema_version"] == CURRENT_SCHEMA_VERSION
    assert bran["psychology"] == {"trust": 0, "respect": 0, "affection": 0, "fear": 0}
    assert bran["met_player"] is True
    assert "disposition_toward_player" not in bran


def test_migrate_v6_to_v7_rekeys_and_splits_traits():
    # ADR 0009 F4: name backfilled from the old key BEFORE the uuid rekey;
    # descriptives fold into traits; stray is_dead/status lifted defensively.
    v6_state = {
        "meta": {"schema_version": 6, "world_name": "Test"},
        "npcs": {
            "Marta": {
                "role": "Innkeeper",
                "personality": "warm",
                "psychology": {"trust": 10},
                "met_player": True,
                "last_interactions": ["hello"],
            },
            "Old Bandit": {"name": "Old Bandit", "is_dead": True},
            "Drifter": {"status": "removed"},
        },
    }
    migrated = migrate_world_state(v6_state)
    assert migrated["meta"]["schema_version"] == CURRENT_SCHEMA_VERSION
    by_name = {n["name"]: (key, n) for key, n in migrated["npcs"].items()}

    key, marta = by_name["Marta"]  # name backfilled from the old dict key
    assert key != "Marta" and "-" in key  # rekeyed to a uuid
    assert marta["traits"] == {"role": "Innkeeper", "personality": "warm"}
    assert "role" not in marta and "personality" not in marta
    assert marta["lifecycle"] == "alive"
    assert marta["condition"] is None
    assert marta["slug"] is None
    assert marta["last_interactions"] == ["hello"]  # engine fields untouched

    assert by_name["Old Bandit"][1]["lifecycle"] == "dead"
    assert "is_dead" not in by_name["Old Bandit"][1]
    assert by_name["Drifter"][1]["lifecycle"] == "removed"
    assert "status" not in by_name["Drifter"][1]


def test_migrate_up_to_date():
    v4_state = {
        "meta": {"schema_version": 7, "world_name": "Test"},
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
    assert migrated["meta"]["schema_version"] == CURRENT_SCHEMA_VERSION
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
