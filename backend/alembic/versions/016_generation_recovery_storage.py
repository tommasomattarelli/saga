"""Persist durable memory generation recovery material."""

from pathlib import Path

from alembic import op

revision = "016_gen_recovery_storage"
down_revision = "015_gen_format_prefs"
branch_labels = None
depends_on = None


def _run_sql_file(name: str) -> None:
    path = Path(__file__).resolve().parents[1] / "sql" / name
    for statement in path.read_text(encoding="utf-8").split("\n\n"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _run_sql_file("016_generation_recovery_storage.sql")


def downgrade() -> None:
    _run_sql_file("016_generation_recovery_storage_rollback.sql")
