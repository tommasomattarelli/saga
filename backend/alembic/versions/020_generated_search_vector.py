"""Derive memory_facts.search_vector from content in Postgres.

Revision ID: 020_generated_search_vector
Revises: 019_memory_payload_retention
"""

from alembic import op

revision = "020_generated_search_vector"
down_revision = "019_memory_payload_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX ix_memory_facts_search_vector")
    op.execute("ALTER TABLE memory_facts DROP COLUMN search_vector")
    op.execute(
        "ALTER TABLE memory_facts ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, content)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_memory_facts_search_vector ON memory_facts USING gin (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_memory_facts_search_vector")
    op.execute("ALTER TABLE memory_facts DROP COLUMN search_vector")
    op.execute("ALTER TABLE memory_facts ADD COLUMN search_vector tsvector")
    op.execute(
        "CREATE INDEX ix_memory_facts_search_vector ON memory_facts USING gin (search_vector)"
    )
