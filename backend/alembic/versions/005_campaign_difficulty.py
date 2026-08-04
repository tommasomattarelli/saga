"""Rename campaigns.death_mode to difficulty (ADR 0003 B8).

The three behaviours survive, renamed: cronista→easy, destino→medium, ironman→hard.
Also renames the world_state fate counter, whose old name carried the old vocabulary.

Revision ID: 005_campaign_difficulty
Revises: 004_world_model
Create Date: 2026-08-04
"""

import sqlalchemy as sa

from alembic import op

revision = "005_campaign_difficulty"
down_revision = "004_world_model"
branch_labels = None
depends_on = None

_DIFFICULTY = sa.Enum("easy", "medium", "hard", name="difficulty")
_DEATH_MODE = sa.Enum("ironman", "destino", "cronista", name="deathmode")

_FORWARD = {"cronista": "easy", "destino": "medium", "ironman": "hard"}
_BACK = {v: k for k, v in _FORWARD.items()}


def _recolumn(mapping: dict[str, str], old: str, new: str, new_type: sa.Enum) -> None:
    new_type.create(op.get_bind(), checkfirst=True)
    op.add_column("campaigns", sa.Column(new, new_type, nullable=True))
    case = " ".join(f"WHEN '{src}' THEN '{dst}'" for src, dst in mapping.items())
    op.execute(
        f"UPDATE campaigns SET {new} = (CASE {old}::text {case} END)::{new_type.name}"  # noqa: S608
    )
    op.alter_column("campaigns", new, nullable=False)
    op.drop_column("campaigns", old)


def upgrade() -> None:
    _recolumn(_FORWARD, "death_mode", "difficulty", _DIFFICULTY)
    sa.Enum(name="deathmode").drop(op.get_bind(), checkfirst=True)
    op.execute(
        """
        UPDATE campaigns
        SET world_state = (world_state - 'destino_lives')
            || jsonb_build_object('fate_interventions_left', world_state->'destino_lives')
        WHERE world_state IS NOT NULL AND world_state ? 'destino_lives'
        """
    )


def downgrade() -> None:
    _recolumn(_BACK, "difficulty", "death_mode", _DEATH_MODE)
    sa.Enum(name="difficulty").drop(op.get_bind(), checkfirst=True)
    op.execute(
        """
        UPDATE campaigns
        SET world_state = (world_state - 'fate_interventions_left')
            || jsonb_build_object('destino_lives', world_state->'fate_interventions_left')
        WHERE world_state IS NOT NULL AND world_state ? 'fate_interventions_left'
        """
    )
