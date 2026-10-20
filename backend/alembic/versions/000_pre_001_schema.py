"""Frozen pre-001 application schema.

Revision ID: 000_pre_001_schema
Revises: None
Create Date: 2026-10-20

The DDL below is frozen from the real create_all schema at 94db17d, the parent
of the commit that introduced 001. It intentionally does not import application
models: a historical revision must not change when the current ORM does.
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

revision = "000_pre_001_schema"
down_revision = None
branch_labels = None
depends_on = None

_CAMPAIGN_STATUS = ENUM(
    "ACTIVE",
    "PAUSED",
    "COMPLETED",
    "ABANDONED",
    name="campaignstatus",
    create_type=False,
)
_DEATH_MODE = ENUM(
    "IRONMAN",
    "DESTINO",
    "CRONISTA",
    name="deathmode",
    create_type=False,
)


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
    bind = op.get_bind()
    for enum_type in (_CAMPAIGN_STATUS, _DEATH_MODE):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("preferred_language", sa.String(5), nullable=False),
        sa.Column("openai_api_key_enc", sa.Text(), nullable=True),
        sa.Column("anthropic_api_key_enc", sa.Text(), nullable=True),
        sa.Column("google_api_key_enc", sa.Text(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "campaigns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("template_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", _CAMPAIGN_STATUS, nullable=False),
        sa.Column("death_mode", _DEATH_MODE, nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("character_data", JSONB(), nullable=False),
        sa.Column("world_state", JSONB(), nullable=False),
        sa.Column("quests", JSONB(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_campaigns_user_id", "campaigns", ["user_id"])

    op.create_table(
        "templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("author", sa.String(100), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("tags", JSONB(), nullable=False),
        sa.Column("content", JSONB(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_templates_slug", "templates", ["slug"], unique=True)

    op.create_table(
        "achievements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_achievements_user_id", "achievements", ["user_id"])

    op.create_table(
        "profile_stats",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("total_turns", sa.Integer(), nullable=False),
        sa.Column("total_campaigns", sa.Integer(), nullable=False),
        sa.Column("total_play_time_minutes", sa.Integer(), nullable=False),
        sa.Column("stats_data", JSONB(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_profile_stats_user_id", "profile_stats", ["user_id"], unique=True)

    op.create_table(
        "turns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id"), nullable=False
        ),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("player_action", sa.Text(), nullable=False),
        sa.Column("narration", sa.Text(), nullable=False),
        sa.Column("dice_rolls", JSONB(), nullable=True),
        sa.Column("companion_actions", JSONB(), nullable=True),
        sa.Column("world_updates", JSONB(), nullable=True),
        sa.Column("scene_mood", sa.String(50), nullable=True),
        sa.Column("suggested_actions", JSONB(), nullable=True),
        sa.Column("model_used", sa.String(50), nullable=False),
        sa.Column("importance_score", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(384), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_turns_campaign_id", "turns", ["campaign_id"])

    op.create_table(
        "saves",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id"), nullable=False
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("scene_summary", sa.Text(), nullable=False),
        sa.Column("is_auto", sa.Boolean(), nullable=False),
        sa.Column("campaign_snapshot", JSONB(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_saves_campaign_id", "saves", ["campaign_id"])


def downgrade() -> None:
    op.drop_table("saves")
    op.drop_table("turns")
    op.drop_table("profile_stats")
    op.drop_table("achievements")
    op.drop_table("templates", if_exists=True)
    op.drop_table("campaigns")
    op.drop_table("users")
    _DEATH_MODE.drop(op.get_bind(), checkfirst=True)
    _CAMPAIGN_STATUS.drop(op.get_bind(), checkfirst=True)
