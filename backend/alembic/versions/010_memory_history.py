"""Add immutable history identities and explicit memory policy snapshots."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "010_memory_history"
down_revision = "009_campaign_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("memory_policies", "history_continuations"):
        columns = [
            sa.Column("id", pg.UUID(), primary_key=True),
            sa.Column(
                "campaign_id",
                pg.UUID(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        ]
        if table == "memory_policies":
            columns.extend(
                [
                    sa.Column("schema_version", sa.Integer(), nullable=False),
                    sa.Column("payload", pg.JSONB(), nullable=False),
                    sa.Column("payload_hash", sa.String(64), nullable=False),
                ]
            )
        else:
            columns.extend(
                [
                    sa.Column("parent_continuation_id", pg.UUID()),
                    sa.Column("fork_head_turn_id", pg.UUID()),
                ]
            )
        op.create_table(
            table,
            *columns,
            sa.UniqueConstraint("id", "campaign_id", name=f"uq_{table}_id_campaign"),
        )
        op.create_index(f"ix_{table}_campaign_id", table, ["campaign_id"])
    op.create_check_constraint(
        "ck_memory_policies_schema_version", "memory_policies", "schema_version = 1"
    )
    op.create_unique_constraint(
        "uq_memory_policies_campaign_snapshot", "memory_policies", ["campaign_id"]
    )
    op.create_index(
        "uq_history_continuations_root",
        "history_continuations",
        ["campaign_id"],
        unique=True,
        postgresql_where=sa.text("parent_continuation_id IS NULL"),
    )
    op.create_check_constraint(
        "ck_memory_policies_hash", "memory_policies", "payload_hash ~ '^[0-9a-f]{64}$'"
    )
    op.create_check_constraint(
        "ck_memory_policies_batch_size",
        "memory_policies",
        "payload ? 'batch_turns' AND jsonb_typeof(payload->'batch_turns') = 'number' AND (payload->>'batch_turns')::integer > 0",
    )
    op.create_check_constraint(
        "ck_history_continuations_root",
        "history_continuations",
        "parent_continuation_id IS NOT NULL OR fork_head_turn_id IS NULL",
    )
    op.create_check_constraint(
        "ck_history_continuations_not_self",
        "history_continuations",
        "id <> parent_continuation_id",
    )
    for column, target in (
        ("parent_continuation_id", "history_continuations"),
        ("fork_head_turn_id", "turns"),
    ):
        op.create_foreign_key(
            f"fk_history_continuations_{'parent' if target == 'history_continuations' else 'fork'}",
            "history_continuations",
            target,
            [column, "campaign_id"],
            ["id", "campaign_id"],
            deferrable=True,
            initially="DEFERRED",
        )
        op.create_index(f"ix_history_continuations_{column}", "history_continuations", [column])

    for column in ("continuation_id", "parent_turn_id"):
        op.add_column("turns", sa.Column(column, pg.UUID()))
        op.create_index(f"ix_turns_{column}", "turns", [column])
    op.add_column("turns", sa.Column("history_depth", sa.Integer()))
    op.add_column(
        "turns",
        sa.Column("parent_depth", sa.Integer(), sa.Computed("history_depth - 1", persisted=True)),
    )
    op.create_unique_constraint(
        "uq_turns_id_campaign_depth", "turns", ["id", "campaign_id", "history_depth"]
    )
    op.create_foreign_key(
        "fk_turns_continuation",
        "turns",
        "history_continuations",
        ["continuation_id", "campaign_id"],
        ["id", "campaign_id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        "fk_turns_parent_depth",
        "turns",
        "turns",
        ["parent_turn_id", "campaign_id", "parent_depth"],
        ["id", "campaign_id", "history_depth"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_check_constraint(
        "ck_turns_history_contract",
        "turns",
        "(continuation_id IS NULL AND parent_turn_id IS NULL AND history_depth IS NULL) OR "
        "(continuation_id IS NOT NULL AND history_depth IS NOT NULL AND "
        "((parent_turn_id IS NULL AND history_depth=1) OR (parent_turn_id IS NOT NULL AND history_depth>1)))",
    )
    op.create_index(
        "uq_turns_continuation_parent",
        "turns",
        ["continuation_id", "parent_turn_id"],
        unique=True,
        postgresql_where=sa.text("continuation_id IS NOT NULL"),
        postgresql_nulls_not_distinct=True,
    )

    for table, columns in (
        ("campaigns", ("memory_policy_id", "active_continuation_id", "active_head_turn_id")),
        ("saves", ("memory_policy_id", "continuation_id", "head_turn_id")),
    ):
        for column, target in zip(
            columns, ("memory_policies", "history_continuations", "turns"), strict=True
        ):
            op.add_column(table, sa.Column(column, pg.UUID()))
            op.create_index(f"ix_{table}_{column}", table, [column])
            suffix = column.removesuffix("_id").replace("head_turn", "head")
            op.create_foreign_key(
                f"fk_{table}_{suffix}",
                table,
                target,
                [column, "id" if table == "campaigns" else "campaign_id"],
                ["id", "campaign_id"],
                deferrable=True,
                initially="DEFERRED",
            )
    op.add_column(
        "campaigns", sa.Column("context_epoch", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "campaigns",
        sa.Column("fork_on_next_action", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_check_constraint("ck_campaigns_context_epoch", "campaigns", "context_epoch >= 0")
    op.create_check_constraint(
        "ck_campaigns_history_contract",
        "campaigns",
        "(memory_policy_id IS NULL AND active_continuation_id IS NULL AND active_head_turn_id IS NULL) OR (memory_policy_id IS NOT NULL AND active_continuation_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_saves_history_contract",
        "saves",
        "(memory_policy_id IS NULL AND continuation_id IS NULL AND head_turn_id IS NULL) OR (memory_policy_id IS NOT NULL AND continuation_id IS NOT NULL)",
    )
    sql = Path(__file__).resolve().parents[1] / "sql" / "010_history_integrity.sql"
    for statement in sql.read_text().split("\n\n"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM history_continuations) OR EXISTS (SELECT 1 FROM memory_policies)"
            )
        )
        .scalar()
    ):
        raise RuntimeError("Cannot discard persisted history or memory policies during downgrade.")
    for table, trigger in (
        ("campaigns", "history_selection"),
        ("saves", "history_selection"),
        ("turns", "history_turn"),
        ("history_continuations", "history_continuation"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    for table in ("memory_policies", "history_continuations", "turns", "saves"):
        op.execute(f"DROP TRIGGER IF EXISTS history_immutable ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS history_preserved ON {table}")
    for function in (
        "saga_check_history_selection()",
        "saga_check_history_turn()",
        "saga_check_continuation()",
        "saga_continuation_contains(uuid,uuid,uuid)",
        "saga_history_contains(uuid,uuid,uuid)",
        "saga_history_immutable()",
        "saga_history_preserved()",
    ):
        op.execute(f"DROP FUNCTION {function}")
    for table, suffixes in (
        ("campaigns", ("memory_policy", "active_continuation", "active_head")),
        ("saves", ("memory_policy", "continuation", "head")),
    ):
        for suffix in suffixes:
            op.drop_constraint(f"fk_{table}_{suffix}", table, type_="foreignkey")
        op.drop_constraint(f"ck_{table}_history_contract", table, type_="check")
    op.drop_constraint("ck_campaigns_context_epoch", "campaigns", type_="check")
    for column in (
        "memory_policy_id",
        "active_continuation_id",
        "active_head_turn_id",
        "context_epoch",
        "fork_on_next_action",
    ):
        op.drop_column("campaigns", column)
    for column in ("memory_policy_id", "continuation_id", "head_turn_id"):
        op.drop_column("saves", column)
    for constraint in (
        "fk_turns_continuation",
        "fk_turns_parent_depth",
        "uq_turns_id_campaign_depth",
        "ck_turns_history_contract",
    ):
        op.drop_constraint(constraint, "turns")
    op.drop_index("uq_turns_continuation_parent", "turns")
    for column in ("parent_depth", "parent_turn_id", "history_depth", "continuation_id"):
        op.drop_column("turns", column)
    op.drop_table("history_continuations")
    op.drop_table("memory_policies")
