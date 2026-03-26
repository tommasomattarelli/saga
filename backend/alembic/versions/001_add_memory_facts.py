"""Add memory_facts table for atomic fact storage.

Revision ID: 001_memory_facts
Revises: None
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID

revision = "001_memory_facts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_facts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("entity_name", sa.String(200), index=True, nullable=False),
        sa.Column("entity_type", sa.String(50), index=True, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("search_vector", TSVECTOR, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_memory_facts_search_vector", "memory_facts", ["search_vector"], postgresql_using="gin")
    op.create_index("ix_memory_facts_campaign_entity", "memory_facts", ["campaign_id", "entity_name"])


def downgrade() -> None:
    op.drop_index("ix_memory_facts_campaign_entity", table_name="memory_facts")
    op.drop_index("ix_memory_facts_search_vector", table_name="memory_facts")
    op.drop_table("memory_facts")
