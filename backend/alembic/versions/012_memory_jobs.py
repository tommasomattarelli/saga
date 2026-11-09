"""Persist memory jobs and provider calls (part 1 of ADR 0020 S1 job storage).

The second part, added in a follow-up commit, persists memory generations
(per-provider calls) and turn request claims.
"""

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
               OR EXISTS (SELECT 1 FROM memory_job_attempts) THEN
                RAISE EXCEPTION 'Cannot downgrade memory jobs while persisted job data exists.';
            END IF;
        END
        $$;
        """
    )
    op.execute("DROP TRIGGER memory_job_sources ON memory_jobs")
    op.execute("DROP FUNCTION saga_memory_job_sources()")
    op.execute("DROP TRIGGER memory_job_guard ON memory_jobs")
    op.execute("DROP FUNCTION saga_memory_job_guard()")
    op.drop_table("memory_job_attempts")
    op.drop_table("memory_jobs")
