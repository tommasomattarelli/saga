"""Persist claim-time clock for frozen relational edge references (ADR 0023)."""

import sqlalchemy as sa
from alembic import op

revision = "021_turn_game_minutes"
down_revision = "020_generated_search_vector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("turns", sa.Column("game_minutes", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_turns_game_minutes", "turns", "game_minutes IS NULL OR game_minutes >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_turns_game_minutes", "turns", type_="check")
    op.drop_column("turns", "game_minutes")
