"""Persist ordered memory partitions, immutable documents, and coverage cursors."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "011_memory_documents"
down_revision = "010_memory_history"
branch_labels = None
depends_on = None


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column(
            "campaign_id",
            pg.UUID(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _fk(name: str, table: str, target: str, columns: list[str], target_columns: list[str]) -> None:
    op.create_foreign_key(
        name, table, target, columns, target_columns, deferrable=True, initially="DEFERRED"
    )


def _run_sql_file(name: str) -> None:
    path = Path(__file__).resolve().parents[1] / "sql" / name
    for statement in path.read_text(encoding="utf-8").split("\n\n"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    op.create_table(
        "memory_batches",
        *_base(),
        sa.Column("policy_id", pg.UUID(), nullable=False),
        sa.Column("previous_batch_id", pg.UUID()),
        sa.Column("source_head_turn_id", pg.UUID(), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("id", "campaign_id", name="uq_memory_batches_id_campaign"),
        sa.UniqueConstraint(
            "id", "campaign_id", "policy_id", name="uq_memory_batches_id_campaign_policy"
        ),
        sa.CheckConstraint("id <> previous_batch_id", name="ck_memory_batches_not_self"),
        sa.CheckConstraint("manifest_hash ~ '^[0-9a-f]{64}$'", name="ck_memory_batches_hash"),
    )
    _fk(
        "fk_memory_batches_policy",
        "memory_batches",
        "memory_policies",
        ["policy_id", "campaign_id"],
        ["id", "campaign_id"],
    )
    _fk(
        "fk_memory_batches_previous",
        "memory_batches",
        "memory_batches",
        ["previous_batch_id", "campaign_id", "policy_id"],
        ["id", "campaign_id", "policy_id"],
    )
    _fk(
        "fk_memory_batches_source_head",
        "memory_batches",
        "turns",
        ["source_head_turn_id", "campaign_id"],
        ["id", "campaign_id"],
    )
    op.create_index(
        "uq_memory_batches_input",
        "memory_batches",
        ["campaign_id", "policy_id", "previous_batch_id", "source_head_turn_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_table(
        "memory_batch_turns",
        sa.Column("batch_id", pg.UUID(), primary_key=True),
        sa.Column("ordinal", sa.Integer(), primary_key=True),
        sa.Column(
            "campaign_id",
            pg.UUID(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_id", pg.UUID(), nullable=False),
        sa.UniqueConstraint(
            "batch_id", "turn_id", "campaign_id", name="uq_memory_batch_turns_source"
        ),
        sa.UniqueConstraint("batch_id", "turn_id", name="uq_memory_batch_turns_batch_turn"),
        sa.CheckConstraint("ordinal > 0", name="ck_memory_batch_turns_ordinal"),
    )
    _fk(
        "fk_memory_batch_turns_batch",
        "memory_batch_turns",
        "memory_batches",
        ["batch_id", "campaign_id"],
        ["id", "campaign_id"],
    )
    _fk(
        "fk_memory_batch_turns_turn",
        "memory_batch_turns",
        "turns",
        ["turn_id", "campaign_id"],
        ["id", "campaign_id"],
    )
    for table in ("memory_summaries", "memory_global_checkpoints"):
        columns = [
            *_base(),
            sa.Column("policy_id", pg.UUID(), nullable=False),
            sa.Column("batch_id", pg.UUID(), nullable=False),
            sa.Column("payload", pg.JSONB(), nullable=False),
            sa.Column("generation_id", pg.UUID(), nullable=False),
            sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        ]
        if table == "memory_global_checkpoints":
            columns.append(sa.Column("previous_checkpoint_id", pg.UUID()))
        op.create_table(table, *columns)
        op.create_check_constraint(f"ck_{table}_schema_version", table, "schema_version = 1")
        _fk(
            f"fk_{table}_batch",
            table,
            "memory_batches",
            ["batch_id", "campaign_id", "policy_id"],
            ["id", "campaign_id", "policy_id"],
        )
    op.create_unique_constraint("uq_memory_summaries_batch", "memory_summaries", ["batch_id"])
    op.create_check_constraint(
        "ck_memory_summaries_payload",
        "memory_summaries",
        "jsonb_typeof(payload) = 'object' AND payload ? 'text' AND payload - 'text' = '{}'::jsonb AND jsonb_typeof(payload->'text')='string' AND btrim(payload->>'text') <> ''",
    )
    op.create_unique_constraint(
        "uq_memory_global_checkpoints_scope",
        "memory_global_checkpoints",
        ["id", "campaign_id", "policy_id"],
    )
    _fk(
        "fk_memory_global_checkpoints_previous",
        "memory_global_checkpoints",
        "memory_global_checkpoints",
        ["previous_checkpoint_id", "campaign_id", "policy_id"],
        ["id", "campaign_id", "policy_id"],
    )
    op.create_check_constraint(
        "ck_memory_global_checkpoints_not_self",
        "memory_global_checkpoints",
        "id <> previous_checkpoint_id",
    )
    op.create_index(
        "uq_memory_global_checkpoints_transition",
        "memory_global_checkpoints",
        ["campaign_id", "policy_id", "previous_checkpoint_id", "batch_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_table(
        "memory_states",
        *_base(),
        sa.Column("policy_id", pg.UUID(), nullable=False),
        sa.Column("context_epoch", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("global_checkpoint_id", pg.UUID()),
        sa.Column("last_compacted_batch_id", pg.UUID()),
        sa.UniqueConstraint("id", "campaign_id", "policy_id", name="uq_memory_states_scope"),
        sa.CheckConstraint(
            "context_epoch >= 0 AND revision >= 0", name="ck_memory_states_counters"
        ),
        sa.CheckConstraint(
            "global_checkpoint_id IS NULL OR last_compacted_batch_id IS NOT NULL",
            name="ck_memory_states_checkpoint_has_batch",
        ),
    )
    _fk(
        "fk_memory_states_policy",
        "memory_states",
        "memory_policies",
        ["policy_id", "campaign_id"],
        ["id", "campaign_id"],
    )
    _fk(
        "fk_memory_states_checkpoint",
        "memory_states",
        "memory_global_checkpoints",
        ["global_checkpoint_id", "campaign_id", "policy_id"],
        ["id", "campaign_id", "policy_id"],
    )
    _fk(
        "fk_memory_states_batch",
        "memory_states",
        "memory_batches",
        ["last_compacted_batch_id", "campaign_id", "policy_id"],
        ["id", "campaign_id", "policy_id"],
    )
    op.add_column("campaigns", sa.Column("active_memory_state_id", pg.UUID()))
    _fk(
        "fk_campaigns_active_memory_state",
        "campaigns",
        "memory_states",
        ["active_memory_state_id", "id", "memory_policy_id"],
        ["id", "campaign_id", "policy_id"],
    )
    op.create_check_constraint(
        "ck_campaigns_memory_state_policy",
        "campaigns",
        "active_memory_state_id IS NULL OR memory_policy_id IS NOT NULL",
    )
    for column, target, suffix in (
        ("global_checkpoint_id", "memory_global_checkpoints", "checkpoint"),
        ("last_compacted_batch_id", "memory_batches", "batch"),
    ):
        op.add_column("saves", sa.Column(column, pg.UUID()))
        _fk(
            f"fk_saves_{suffix}",
            "saves",
            target,
            [column, "campaign_id", "memory_policy_id"],
            ["id", "campaign_id", "policy_id"],
        )
    op.create_check_constraint(
        "ck_saves_memory_policy",
        "saves",
        "(global_checkpoint_id IS NULL AND last_compacted_batch_id IS NULL) OR memory_policy_id IS NOT NULL",
    )
    for table, columns in {
        "memory_batches": ["campaign_id", "policy_id", "previous_batch_id", "source_head_turn_id"],
        "memory_batch_turns": ["campaign_id", "turn_id"],
        "memory_summaries": ["campaign_id", "policy_id", "generation_id"],
        "memory_global_checkpoints": [
            "campaign_id",
            "policy_id",
            "batch_id",
            "previous_checkpoint_id",
            "generation_id",
        ],
        "memory_states": [
            "campaign_id",
            "policy_id",
            "global_checkpoint_id",
            "last_compacted_batch_id",
        ],
        "campaigns": ["active_memory_state_id"],
        "saves": ["global_checkpoint_id", "last_compacted_batch_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    for name in (
        "011_fact_schema.sql",
        "011_batch_integrity.sql",
        "011_document_integrity.sql",
        "011_cursor_integrity.sql",
    ):
        _run_sql_file(name)


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM memory_batches) OR EXISTS (SELECT 1 FROM memory_states)"
            )
        )
        .scalar()
    ):
        raise RuntimeError("Cannot discard memory partitions or contexts during downgrade.")
    for table, triggers in {
        "memory_batches": ["memory_batch_integrity", "memory_immutable"],
        "memory_batch_turns": ["memory_batch_integrity", "memory_immutable"],
        "memory_summaries": ["memory_immutable"],
        "memory_fact_sources": ["memory_fact_integrity", "memory_immutable"],
        "memory_facts": ["memory_fact_integrity", "memory_immutable"],
        "memory_global_checkpoints": ["memory_checkpoint_integrity", "memory_immutable"],
        "memory_states": ["memory_cursor_integrity", "memory_state_guard"],
        "campaigns": ["memory_cursor_integrity"],
        "saves": ["memory_cursor_integrity"],
    }.items():
        for trigger in triggers:
            op.execute(f"DROP TRIGGER {trigger} ON {table}")
        if "memory_immutable" in triggers:
            op.execute(f"DROP TRIGGER memory_preserved ON {table}")
    for function in (
        "saga_check_memory_cursor()",
        "saga_validate_memory_cursor(uuid,uuid,uuid,uuid,uuid)",
        "saga_check_memory_checkpoint()",
        "saga_check_memory_fact()",
        "saga_check_memory_batch()",
        "saga_memory_immutable()",
        "saga_memory_state_guard()",
    ):
        op.execute(f"DROP FUNCTION {function}")
    op.drop_constraint("fk_campaigns_active_memory_state", "campaigns", type_="foreignkey")
    op.drop_constraint("ck_campaigns_memory_state_policy", "campaigns", type_="check")
    op.drop_column("campaigns", "active_memory_state_id")
    op.drop_constraint("ck_saves_memory_policy", "saves", type_="check")
    for column, suffix in (
        ("global_checkpoint_id", "checkpoint"),
        ("last_compacted_batch_id", "batch"),
    ):
        op.drop_constraint(f"fk_saves_{suffix}", "saves", type_="foreignkey")
        op.drop_column("saves", column)
    op.drop_table("memory_fact_sources")
    _run_sql_file("011_fact_downgrade.sql")
    for table in (
        "memory_states",
        "memory_global_checkpoints",
        "memory_summaries",
        "memory_batch_turns",
        "memory_batches",
    ):
        op.drop_table(table)
