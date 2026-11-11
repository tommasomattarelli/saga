import uuid
from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TurnRequest(Base, TimestampMixin):
    __tablename__ = "turn_requests"
    __table_args__ = (
        UniqueConstraint("campaign_id", "request_id", name="uq_turn_requests_campaign_request"),
        UniqueConstraint("request_id", "campaign_id", name="uq_turn_requests_request_campaign"),
        ForeignKeyConstraint(
            ["starting_head_turn_id", "campaign_id"],
            ["turns.id", "turns.campaign_id"],
            name="fk_turn_requests_start_head_campaign",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["result_turn_id", "campaign_id"],
            ["turns.id", "turns.campaign_id"],
            name="fk_turn_requests_result_turn_campaign",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "state IN ('running', 'committed', 'interrupted', 'invalidated')",
            name="ck_turn_requests_state",
        ),
        CheckConstraint(
            "(state = 'running' AND execution_token IS NOT NULL AND execution_expires_at IS NOT NULL)"
            " OR (state <> 'running' AND execution_token IS NULL AND execution_expires_at IS NULL)",
            name="ck_turn_requests_execution_state",
        ),
        CheckConstraint(
            "(state = 'committed') = (result_turn_id IS NOT NULL) "
            "AND (state <> 'running' OR claimed_turn_number IS NOT NULL)",
            name="ck_turn_requests_result_state",
        ),
        CheckConstraint(
            "claimed_turn_number IS NULL OR claimed_turn_number > 0",
            name="ck_turn_requests_claimed_number",
        ),
        CheckConstraint("context_epoch >= 0", name="ck_turn_requests_context_epoch"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="ck_turn_requests_payload_hash"),
        CheckConstraint(
            "response_payload IS NULL OR (state = 'committed' AND jsonb_typeof(response_payload) = 'object')",
            name="ck_turn_requests_response_state",
        ),
        Index(
            "uq_turn_requests_campaign_running",
            "campaign_id",
            unique=True,
            postgresql_where=text("state = 'running'"),
        ),
        Index("ix_turn_requests_start_head_scope", "starting_head_turn_id", "campaign_id"),
        Index("ix_turn_requests_result_turn_scope", "result_turn_id", "campaign_id"),
        Index("ix_turn_requests_campaign_id", "campaign_id"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    payload_hash: Mapped[str] = mapped_column(String(64))
    starting_head_turn_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    context_epoch: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16))
    execution_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    execution_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    claimed_turn_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    response_payload: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB, nullable=True)
