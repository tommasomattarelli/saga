"""Bind durable sends to derived identities and preserve typed receipts."""

from pathlib import Path

from alembic import op

revision = "017_gen_ledger_contracts"
down_revision = "016_gen_recovery_storage"
branch_labels = None
depends_on = None


def _run_sql_file(name: str) -> None:
    path = Path(__file__).resolve().parents[1] / "sql" / name
    for statement in path.read_text(encoding="utf-8").split("\n\n"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _run_sql_file("017_generation_ledger_contracts.sql")


def downgrade() -> None:
    _run_sql_file("017_generation_ledger_contracts_rollback.sql")
