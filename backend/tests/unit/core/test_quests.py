"""ADR 0019 A2-A3 — the canonical quest registry and its transitions."""

import pytest
from pydantic import ValidationError

from app.core.quests import apply_quest_update
from app.models.quest import QuestRecord, QuestRegistry, QuestStatus


def _registry() -> QuestRegistry:
    return QuestRegistry(
        active=[
            QuestRecord(
                id="who_am_i",
                name="Who Am I?",
                description="Discover your identity.",
                objectives=["Ask the villagers", "Examine the shrine"],
            )
        ]
    )


def _only(registry: QuestRegistry, status: QuestStatus) -> list[QuestRecord]:
    return getattr(registry, status.value)


def test_a_new_active_quest_needs_a_non_empty_display_name():
    registry, error = apply_quest_update(
        QuestRegistry(), quest_id="dragon_hunt", status="active", name=" "
    )
    assert error == "Quest 'dragon_hunt' does not exist; a name is required to start it."
    assert registry == QuestRegistry()


def test_a_new_active_quest_starts_empty_of_objectives():
    registry, error = apply_quest_update(
        QuestRegistry(), quest_id="dragon_hunt", status="active", name="Dragon Hunt"
    )
    assert error is None
    assert _only(registry, QuestStatus.ACTIVE) == [
        QuestRecord(id="dragon_hunt", name="Dragon Hunt", description="", objectives=[])
    ]


@pytest.mark.parametrize("status", ["completed", "failed", "abandoned"])
def test_an_unknown_quest_cannot_be_concluded(status):
    original = QuestRegistry()
    registry, error = apply_quest_update(
        original, quest_id="dragon_hunt", status=status, name="Dragon Hunt"
    )
    assert error == "Quest 'dragon_hunt' does not exist; only an active quest can start it."
    assert registry is original


def test_an_invalid_id_is_rejected_without_mutation():
    original = QuestRegistry()
    registry, error = apply_quest_update(
        original, quest_id="Dragon Hunt", status="active", name="Dragon Hunt"
    )
    assert error is not None
    assert "lowercase" in error
    assert registry is original


def test_an_unknown_status_is_rejected_without_mutation():
    original = _registry()
    registry, error = apply_quest_update(original, quest_id="who_am_i", status="paused")
    assert error is not None
    assert registry is original


def test_an_omitted_description_preserves_and_an_empty_string_clears():
    registry = _registry()

    kept, error = apply_quest_update(registry, quest_id="who_am_i", status="active")
    assert error is None
    assert kept.active[0].description == "Discover your identity."

    cleared, error = apply_quest_update(kept, quest_id="who_am_i", status="active", description="")
    assert error is None
    assert cleared.active[0].description == ""


def test_moving_a_quest_keeps_one_complete_record():
    registry = _registry()
    objectives = list(registry.active[0].objectives)

    for status in ["completed", "failed", "abandoned", "active"]:
        registry, error = apply_quest_update(registry, quest_id="who_am_i", status=status)
        assert error is None
        assert len(_only(registry, QuestStatus(status))) == 1

    record = registry.active[0]
    assert record.name == "Who Am I?"
    assert record.objectives == objectives
    assert all(
        not _only(registry, status)
        for status in (QuestStatus.COMPLETED, QuestStatus.FAILED, QuestStatus.ABANDONED)
    )


def test_repeated_calls_never_duplicate_a_record():
    registry = _registry()
    for _ in range(3):
        registry, error = apply_quest_update(registry, quest_id="who_am_i", status="active")
        assert error is None
    assert len(registry.active) == 1


def test_distinct_ids_may_share_a_display_name():
    registry, error = apply_quest_update(
        QuestRegistry(), quest_id="dragon_hunt", status="active", name="Dragon Hunt"
    )
    assert error is None
    registry, error = apply_quest_update(
        registry, quest_id="dragon_hunt_on_winter", status="active", name="Dragon Hunt"
    )
    assert error is None
    assert {q.id for q in registry.active} == {"dragon_hunt", "dragon_hunt_on_winter"}


def test_ids_are_unique_across_all_four_lists():
    with pytest.raises(ValidationError):
        QuestRegistry(
            active=[QuestRecord(id="dragon_hunt", name="Dragon Hunt")],
            completed=[QuestRecord(id="dragon_hunt", name="Dragon Hunt")],
        )
