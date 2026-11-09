from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.campaign_language import default_campaign_language
from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.save import Save
    from app.models.turn import Turn
    from app.models.user import User


class CampaignStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class Difficulty(StrEnum):
    """ADR 0003 B8 — governs the death policy only; the math is identical throughout."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Campaign(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "campaigns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["memory_policy_id", "id"],
            ["memory_policies.id", "memory_policies.campaign_id"],
            name="fk_campaigns_memory_policy",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["active_continuation_id", "id"],
            ["history_continuations.id", "history_continuations.campaign_id"],
            name="fk_campaigns_active_continuation",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["active_head_turn_id", "id"],
            ["turns.id", "turns.campaign_id"],
            name="fk_campaigns_active_head",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("context_epoch >= 0", name="ck_campaigns_context_epoch"),
        ForeignKeyConstraint(
            ["active_memory_state_id", "id", "memory_policy_id"],
            ["memory_states.id", "memory_states.campaign_id", "memory_states.policy_id"],
            name="fk_campaigns_active_memory_state",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "active_memory_state_id IS NULL OR memory_policy_id IS NOT NULL",
            name="ck_campaigns_memory_state_policy",
        ),
        ForeignKeyConstraint(
            ["active_action_request_id", "id"],
            ["turn_requests.request_id", "turn_requests.campaign_id"],
            name="fk_campaigns_active_action_request",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "(memory_policy_id IS NULL AND active_continuation_id IS NULL AND active_head_turn_id IS NULL)"
            " OR (memory_policy_id IS NOT NULL AND active_continuation_id IS NOT NULL)",
            name="ck_campaigns_history_contract",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    world_slug: Mapped[str] = mapped_column(String(100))
    # World version stamped at instantiation (ADR 0008 C3b) — saves are frozen
    world_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(
        String(2), default=default_campaign_language, server_default="en"
    )
    status: Mapped[CampaignStatus] = mapped_column(
        SAEnum(CampaignStatus), default=CampaignStatus.ACTIVE
    )
    difficulty: Mapped[Difficulty] = mapped_column(SAEnum(Difficulty))
    turn_number: Mapped[int] = mapped_column(Integer, default=0)
    memory_policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    active_continuation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True
    )
    active_head_turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    active_memory_state_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True
    )
    active_action_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    context_epoch: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fork_on_next_action: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    # Character data (denormalized for fast access)
    character_data: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Static authored world tree, written once at instantiation (ADR 0008 C7/C11);
    # the turn loop never touches it — runtime deltas live in world_state
    world_baseline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # World state overlay (npcs, factions, node status, clock, combat, position)
    world_state: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Active quests
    quests: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Rolling story summary — updated every N turns (see gameplay.global_summary_update_every)
    global_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Persona preset — copied from template at creation, drives DM narrative tone
    persona_preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    persona_xml: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="campaigns")
    turns: Mapped[list[Turn]] = relationship(
        back_populates="campaign",
        lazy="selectin",
        cascade="all, delete-orphan",
        foreign_keys="Turn.campaign_id",
    )
    saves: Mapped[list[Save]] = relationship(
        back_populates="campaign", lazy="selectin", cascade="all, delete-orphan"
    )
