"""Persist memory jobs, provider calls, and turn request claims (ADR 0020 S1)."""

from pathlib import Path

from alembic import op

revision = "012_memory_jobs"
down_revision = "011_memory_documents"
branch_labels = None
depends_on = None


def _run_sql_file(name: str) -> None:
    path = Path(__file__).resolve().parents[1] / "sql" / name
    for statement in path.read_text(encoding="utf-8").split("\n\n"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _run_sql_file("012_job_schema.sql")
    _run_sql_file("012_job_integrity.sql")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM memory_jobs)
               OR EXISTS (SELECT 1 FROM turn_requests)
               OR EXISTS (SELECT 1 FROM memory_generations) THEN
                RAISE EXCEPTION 'Cannot downgrade memory jobs while persisted job data exists.';
            END IF;
        END
        $$;
        """
    )
    op.execute("DROP TRIGGER turn_request_guard ON turn_requests")
    op.execute("DROP FUNCTION saga_turn_request_guard()")
    op.execute("DROP TRIGGER memory_generation_guard ON memory_generations")
    op.execute("DROP FUNCTION saga_memory_generation_guard()")
    op.execute("DROP TRIGGER memory_job_sources ON memory_jobs")
    op.execute("DROP FUNCTION saga_memory_job_sources()")
    op.execute("DROP TRIGGER memory_job_guard ON memory_jobs")
    op.execute("DROP FUNCTION saga_memory_job_guard()")
    op.drop_constraint("fk_campaigns_active_action_request", "campaigns", type_="foreignkey")
    op.drop_column("campaigns", "active_action_request_id")
    op.drop_table("turn_requests")
    for table, constraint in (
        ("memory_global_checkpoints", "fk_memory_global_checkpoints_generation"),
        ("memory_facts", "fk_memory_facts_generation"),
        ("memory_summaries", "fk_memory_summaries_generation"),
    ):
        op.drop_constraint(constraint, table, type_="foreignkey")
    op.drop_table("memory_generations")
    op.drop_table("memory_job_attempts")
    op.drop_table("memory_jobs")
