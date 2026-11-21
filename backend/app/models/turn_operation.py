import uuid

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.memory.operation_contracts import OperationPayload
from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.validated_json import ValidatedJSON


class TurnOperation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "turn_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["turn_id", "campaign_id"],
            ["turns.id", "turns.campaign_id"],
            name="fk_turn_operations_turn_campaign",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("turn_id", "ordinal", name="uq_turn_operations_order"),
        CheckConstraint("ordinal > 0", name="ck_turn_operations_ordinal"),
        CheckConstraint("step IS NULL OR step >= 0", name="ck_turn_operations_step"),
        CheckConstraint("beat IS NULL OR beat >= 0", name="ck_turn_operations_beat"),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND "
            "payload ?& ARRAY['origin','name','outcome','arguments','result','deltas'] AND "
            "jsonb_typeof(payload->'origin') = 'string' AND "
            "jsonb_typeof(payload->'outcome') = 'string' AND "
            "jsonb_typeof(payload->'name') = 'string' AND "
            "payload->>'origin' IN ('tool','npc','finalization') AND "
            "payload->>'outcome' IN ('succeeded','rejected','failed') AND "
            "length(payload->>'name') > 0 AND jsonb_typeof(payload->'arguments') = 'object' AND "
            "jsonb_typeof(payload->'result') = 'object' AND jsonb_typeof(payload->'deltas') = 'array'",
            name="ck_turn_operations_payload",
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        index=True,
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    ordinal: Mapped[int] = mapped_column(Integer)
    step: Mapped[int | None] = mapped_column(Integer)
    beat: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[OperationPayload] = mapped_column(ValidatedJSON(OperationPayload))
