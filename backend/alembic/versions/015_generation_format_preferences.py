"""Persist destination-bound structured generation preferences."""

import sqlalchemy as sa
from alembic import op

revision = "015_gen_format_prefs"
down_revision = "014_turn_request_responses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("generation_allow_json_mode_fallback", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "users", sa.Column("generation_allow_prompt_only_fallback", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "users", sa.Column("generation_format_fingerprint", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "generation_format_fingerprint")
    op.drop_column("users", "generation_allow_prompt_only_fallback")
    op.drop_column("users", "generation_allow_json_mode_fallback")
