"""World model (ADR 0008): baseline column, world identity, drop templates.

Campaigns: template_id -> world_slug, add world_version (C3b stamp) and
world_baseline (static authored tree, written once at instantiation, C7/C11).
Templates are replaced by library Worlds (C4) — drop the table.

Revision ID: 004_world_model
Revises: 003_normalize_npc_disposition
Create Date: 2026-07-06
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "004_world_model"
down_revision = "003_normalize_npc_disposition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("campaigns", "template_id", new_column_name="world_slug")
    op.add_column("campaigns", sa.Column("world_version", sa.String(20), nullable=True))
    op.add_column("campaigns", sa.Column("world_baseline", JSONB, nullable=True))
    op.drop_table("templates")


def downgrade() -> None:
    op.alter_column("campaigns", "world_slug", new_column_name="template_id")
    op.drop_column("campaigns", "world_version")
    op.drop_column("campaigns", "world_baseline")
    # templates table intentionally not recreated — its data came from
    # templates/*.yaml seeding and is rebuilt by the pre-0008 code on startup.
