"""Add personal AI profiles and server-key consents (ADR 0018 A3/A4/B1).

Revision ID: 006_user_provider_settings
Revises: 005_campaign_difficulty
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006_user_provider_settings"
down_revision = "005_campaign_difficulty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("generation_provider", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("generation_model", sa.String(length=200), nullable=True))
    op.add_column(
        "users", sa.Column("generation_local_endpoint", sa.String(length=100), nullable=True)
    )
    op.add_column("users", sa.Column("embedding_provider", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("embedding_model", sa.String(length=200), nullable=True))
    op.add_column(
        "users", sa.Column("embedding_local_endpoint", sa.String(length=100), nullable=True)
    )
    op.add_column("users", sa.Column("server_key_consents", postgresql.JSONB(), nullable=True))
    op.add_column("users", sa.Column("openrouter_api_key_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "openrouter_api_key_enc")
    op.drop_column("users", "server_key_consents")
    op.drop_column("users", "embedding_local_endpoint")
    op.drop_column("users", "embedding_model")
    op.drop_column("users", "embedding_provider")
    op.drop_column("users", "generation_local_endpoint")
    op.drop_column("users", "generation_model")
    op.drop_column("users", "generation_provider")
