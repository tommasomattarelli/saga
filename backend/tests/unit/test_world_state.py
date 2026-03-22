import pytest

from app.memory.world_state import (
    ALLOWED_WORLD_STATE_KEYS,
    merge_world_state,
    migrate_world_state,
    validate_world_state,
)


def test_migrate_v0_to_v1():
    v0_state = {"locations": {"town": "visited"}}
    migrated = migrate_world_state(v0_state)

    assert "meta" in migrated
    assert migrated["meta"]["schema_version"] == 1
    assert migrated["meta"]["world_name"] == "Unknown Land"
    assert migrated["meta"]["current_season"] == "spring"
    assert migrated["locations"]["town"] == "visited"


def test_migrate_up_to_date():
    v1_state = {
        "meta": {"schema_version": 1, "world_name": "Test"},
        "locations": {"town": "visited"},
    }
    migrated = migrate_world_state(v1_state)
    assert migrated == v1_state
    assert migrated is not v1_state  # Should be a deepcopy, Wait, the code says:
    # `state = copy.deepcopy(state)` then if current_version == CURRENT_SCHEMA_VERSION: `return state`
    # So it doesn't return the exact same object reference if it was deepcopied. Let's just check equality.


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
