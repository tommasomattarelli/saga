"""Persist campaign language without changing rewindable snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "009_campaign_language"
down_revision = "008_schema_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaigns", sa.Column("language", sa.String(2), nullable=False, server_default="en")
    )


def downgrade() -> None:
    op.drop_column("campaigns", "language")
