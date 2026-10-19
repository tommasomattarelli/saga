"""Embedding index and per-source vectors (ADR 0018 B3-B6).

Revision ID: 007_embedding_index
Revises: 006_user_provider_settings

Additive: creates embedding_indexes and source_embeddings and backfills the
vectors the pre-change OpenAI/384 writer produced. The legacy Turn.embedding /
MemoryFact.embedding columns are intentionally kept until the callers are
rewired (008, coordinated after gameplay). Downgrade drops only the new objects;
the legacy texts and vectors stay intact.
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "007_embedding_index"
down_revision = "006_user_provider_settings"
branch_labels = None
depends_on = None

_REBUILD_STATE = ENUM(
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="embedding_rebuild_state",
    create_type=False,
)
_SOURCE_TYPE = ENUM("turn", "memory_fact", name="embedding_source_type", create_type=False)
_WORK_STATE = ENUM("pending", "embedded", "failed", name="embedding_work_state", create_type=False)

# Frozen legacy provenance: the pre-change code embedded Turn.summary /
# MemoryFact.content with OpenAI text-embedding-3-small at 384 dimensions. The
# migration carries these as literals on purpose — it must not import future
# application code to stay a stable snapshot.
_LEGACY_PIPELINE = "embed-v1-legacy"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    for enum_type in (_REBUILD_STATE, _SOURCE_TYPE, _WORK_STATE):
        enum_type.create(op.get_bind(), checkfirst=True)

    op.create_unique_constraint("uq_turns_id_campaign", "turns", ["id", "campaign_id"])
    op.create_unique_constraint(
        "uq_memory_facts_id_campaign", "memory_facts", ["id", "campaign_id"]
    )

    op.create_table(
        "embedding_indexes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("endpoint_name", sa.String(100), nullable=True),
        sa.Column("endpoint_identity", sa.String(500), nullable=True),
        sa.Column("pipeline_version", sa.String(50), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rebuild_state", _REBUILD_STATE, nullable=False, server_default="queued"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("claim_token", UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("id", "campaign_id", name="uq_embedding_indexes_id_campaign"),
        sa.CheckConstraint(
            "NOT is_active OR rebuild_state = 'completed'",
            name="ck_embedding_indexes_active_completed",
        ),
        sa.CheckConstraint(
            "dimension IS NULL OR dimension > 0",
            name="ck_embedding_indexes_dimension_positive",
        ),
    )
    op.create_index("ix_embedding_indexes_campaign_id", "embedding_indexes", ["campaign_id"])
    op.create_index(
        "uq_embedding_indexes_campaign_active",
        "embedding_indexes",
        ["campaign_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "uq_embedding_indexes_campaign_open_rebuild",
        "embedding_indexes",
        ["campaign_id"],
        unique=True,
        postgresql_where=sa.text("rebuild_state IN ('queued', 'running')"),
    )

    op.create_table(
        "source_embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("index_id", UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", _SOURCE_TYPE, nullable=False),
        sa.Column("turn_id", UUID(as_uuid=True), nullable=True),
        sa.Column("memory_fact_id", UUID(as_uuid=True), nullable=True),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(), nullable=True),
        sa.Column("work_state", _WORK_STATE, nullable=False, server_default="pending"),
        sa.Column("last_error", sa.String(500), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["index_id", "campaign_id"],
            ["embedding_indexes.id", "embedding_indexes.campaign_id"],
            name="fk_source_embeddings_index_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id", "campaign_id"],
            ["turns.id", "turns.campaign_id"],
            name="fk_source_embeddings_turn_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["memory_fact_id", "campaign_id"],
            ["memory_facts.id", "memory_facts.campaign_id"],
            name="fk_source_embeddings_memory_fact_campaign",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "num_nonnulls(turn_id, memory_fact_id) = 1",
            name="ck_source_embeddings_single_source",
        ),
        sa.CheckConstraint(
            "(source_type = 'turn' AND turn_id IS NOT NULL)"
            " OR (source_type = 'memory_fact' AND memory_fact_id IS NOT NULL)",
            name="ck_source_embeddings_kind_matches_reference",
        ),
        sa.CheckConstraint(
            "work_state <> 'embedded' OR embedding IS NOT NULL",
            name="ck_source_embeddings_embedded_has_vector",
        ),
    )
    op.create_index("ix_source_embeddings_campaign_id", "source_embeddings", ["campaign_id"])
    op.create_index(
        "ix_source_embeddings_index_work_state", "source_embeddings", ["index_id", "work_state"]
    )
    op.create_index(
        "uq_source_embeddings_index_turn",
        "source_embeddings",
        ["index_id", "turn_id"],
        unique=True,
        postgresql_where=sa.text("turn_id IS NOT NULL"),
    )
    op.create_index(
        "uq_source_embeddings_index_memory_fact",
        "source_embeddings",
        ["index_id", "memory_fact_id"],
        unique=True,
        postgresql_where=sa.text("memory_fact_id IS NOT NULL"),
    )

    _backfill_legacy()


def _backfill_legacy() -> None:
    # One legacy index per campaign that actually holds a vector; its dimension
    # is 384 and its pipeline is the pre-change OpenAI one.
    op.execute(
        f"""
        INSERT INTO embedding_indexes
            (id, campaign_id, provider, model, endpoint_name, endpoint_identity,
             pipeline_version, dimension, is_active, rebuild_state)
        SELECT gen_random_uuid(), campaign_id, 'openai', 'text-embedding-3-small', NULL,
               'https://api.openai.com/v1', '{_LEGACY_PIPELINE}', 384, TRUE, 'completed'
        FROM (
            SELECT DISTINCT campaign_id FROM turns WHERE embedding IS NOT NULL
            UNION
            SELECT DISTINCT campaign_id FROM memory_facts WHERE embedding IS NOT NULL
        ) AS legacy_campaigns
        """
    )
    # Turn embeddings hashed Turn.summary; a vector written without text is not
    # representable as a source row and stays only in the legacy column.
    op.execute(
        f"""
        INSERT INTO source_embeddings
            (id, index_id, campaign_id, source_type, turn_id, memory_fact_id,
             text_hash, embedding, work_state)
        SELECT gen_random_uuid(), ei.id, t.campaign_id, 'turn', t.id, NULL,
               encode(sha256(convert_to(t.summary, 'UTF8')), 'hex'), t.embedding, 'embedded'
        FROM turns t
        JOIN embedding_indexes ei
          ON ei.campaign_id = t.campaign_id AND ei.pipeline_version = '{_LEGACY_PIPELINE}'
        WHERE t.embedding IS NOT NULL AND t.summary IS NOT NULL
        """
    )
    # MemoryFact content is NOT NULL, so every non-null vector maps to a source.
    op.execute(
        f"""
        INSERT INTO source_embeddings
            (id, index_id, campaign_id, source_type, turn_id, memory_fact_id,
             text_hash, embedding, work_state)
        SELECT gen_random_uuid(), ei.id, mf.campaign_id, 'memory_fact', NULL, mf.id,
               encode(sha256(convert_to(mf.content, 'UTF8')), 'hex'), mf.embedding, 'embedded'
        FROM memory_facts mf
        JOIN embedding_indexes ei
          ON ei.campaign_id = mf.campaign_id AND ei.pipeline_version = '{_LEGACY_PIPELINE}'
        WHERE mf.embedding IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_table("source_embeddings")
    op.drop_table("embedding_indexes")
    op.drop_constraint("uq_turns_id_campaign", "turns", type_="unique")
    op.drop_constraint("uq_memory_facts_id_campaign", "memory_facts", type_="unique")
    for enum_type in (_WORK_STATE, _SOURCE_TYPE, _REBUILD_STATE):
        enum_type.drop(op.get_bind(), checkfirst=True)
