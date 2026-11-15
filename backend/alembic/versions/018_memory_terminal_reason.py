"""Add structured reasons to definitive memory job exhaustion."""

from pathlib import Path

from alembic import op

revision = "018_memory_terminal_reason"
down_revision = "017_gen_ledger_contracts"
branch_labels = None
depends_on = None


def _run_sql_file(name: str) -> None:
    path = Path(__file__).resolve().parents[1] / "sql" / name
    for statement in path.read_text(encoding="utf-8").split("\n\n"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _run_sql_file("018_memory_terminal_reason.sql")


def downgrade() -> None:
    _run_sql_file("018_memory_terminal_reason_rollback.sql")
