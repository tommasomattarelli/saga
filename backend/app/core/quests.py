"""ADR 0019 A3 — one quest transition implementation for tools and evaluation."""

from __future__ import annotations

from app.models.quest import (
    QuestRecord,
    QuestRegistry,
    QuestStatus,
    is_valid_quest_id,
)

_STATES = ", ".join(status.value for status in QuestStatus)


def _short(value: object) -> str:
    return " ".join(str(value).split())[:40]


def apply_quest_update(
    registry: QuestRegistry,
    *,
    quest_id: str,
    status: str | QuestStatus,
    name: str | None = None,
    description: str | None = None,
) -> tuple[QuestRegistry, str | None]:
    """Move one record between status lists, or create it as active.

    Returns the unchanged registry and a short message on invalid input.
    """
    if not is_valid_quest_id(quest_id):
        return (
            registry,
            f"Invalid quest id '{_short(quest_id)}'. Use lowercase letters, digits and underscores.",
        )
    try:
        target = QuestStatus(status)
    except (TypeError, ValueError):
        return registry, f"Unknown quest status '{_short(status)}'. Valid values: {_STATES}."

    updated = registry.model_copy(deep=True)
    found = updated.find(quest_id)

    if found is None:
        display_name = (name or "").strip()
        if target is not QuestStatus.ACTIVE:
            return (
                registry,
                f"Quest '{quest_id}' does not exist; only an active quest can start it.",
            )
        if not display_name:
            return (
                registry,
                f"Quest '{quest_id}' does not exist; a name is required to start it.",
            )
        getattr(updated, target.value).append(
            QuestRecord(
                id=quest_id,
                name=display_name,
                description=description or "",
                objectives=[],
            )
        )
        return updated, None

    current_status, record = found
    if name is not None and name.strip():
        record.name = name.strip()
    if description is not None:
        record.description = description
    if current_status is not target:
        getattr(updated, current_status.value).remove(record)
        getattr(updated, target.value).append(record)
    return updated, None
