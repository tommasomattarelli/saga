"""Add narration_segments column to turns for inline dice/NPC rendering.

Revision ID: 002_narration_segments
Revises: 001_memory_facts
Create Date: 2026-04-11
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "002_narration_segments"
down_revision = "001_memory_facts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("turns", sa.Column("narration_segments", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("turns", "narration_segments")
