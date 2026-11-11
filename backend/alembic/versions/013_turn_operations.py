"""Persist per-operation memory sources without reconstructing historical turns."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "013_turn_operations"
down_revision = "012_memory_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("turns", sa.Column("operations_version", sa.Integer(), nullable=True))
    op.add_column("turns", sa.Column("operation_count", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_turns_operations_contract",
        "turns",
        "(operations_version IS NULL AND operation_count IS NULL) OR "
        "(operations_version IS NOT NULL AND operations_version=1 AND "
        "operation_count IS NOT NULL AND operation_count >= 0)",
    )
    op.create_table(
        "turn_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("beat", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["turn_id", "campaign_id"],
            ["turns.id", "turns.campaign_id"],
            name="fk_turn_operations_turn_campaign",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint("turn_id", "ordinal", name="uq_turn_operations_order"),
        sa.CheckConstraint("ordinal > 0", name="ck_turn_operations_ordinal"),
        sa.CheckConstraint("step IS NULL OR step >= 0", name="ck_turn_operations_step"),
        sa.CheckConstraint("beat IS NULL OR beat >= 0", name="ck_turn_operations_beat"),
        sa.CheckConstraint(
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
    op.create_index("ix_turn_operations_campaign_id", "turn_operations", ["campaign_id"])
    sql = Path(__file__).resolve().parents[1] / "sql" / "013_operation_integrity.sql"
    for statement in sql.read_text(encoding="utf-8").split("\n\n"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM turns WHERE operations_version IS NOT NULL) THEN
                RAISE EXCEPTION 'Cannot discard recorded turn operation sources.';
            END IF;
        END $$;
    """)
    op.execute("DROP TRIGGER operations_integrity ON turns")
    op.execute("DROP TRIGGER operations_marker_guard ON turns")
    op.drop_table("turn_operations")
    op.execute("DROP FUNCTION saga_operation_integrity()")
    op.execute("DROP FUNCTION saga_operation_immutable()")
    op.execute("DROP FUNCTION saga_operations_marker_guard()")
    op.drop_constraint("ck_turns_operations_contract", "turns", type_="check")
    op.drop_column("turns", "operation_count")
    op.drop_column("turns", "operations_version")
