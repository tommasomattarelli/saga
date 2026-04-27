"""Normalize NPC disposition key in world_state JSONB.

Renames world_state.npcs[*].disposition -> disposition_toward_player for all
campaigns where the legacy key exists without the canonical one.

Revision ID: 003_normalize_npc_disposition
Revises: 002_narration_segments
Create Date: 2026-04-27
"""

from alembic import op

revision = "003_normalize_npc_disposition"
down_revision = "002_narration_segments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # For each campaign row whose world_state.npcs dict has at least one NPC
    # with a "disposition" key but no "disposition_toward_player" key, rebuild
    # the npcs object using jsonb_object_agg + jsonb_set.
    #
    # Strategy:
    #   1. Expand npcs object into (npc_name, npc_data) pairs via jsonb_each.
    #   2. For each NPC value: if it has "disposition" but not
    #      "disposition_toward_player", add the canonical key from the legacy
    #      value and remove the legacy key; otherwise leave unchanged.
    #   3. Re-aggregate into a new npcs object and write back.
    #
    # Rows where world_state is NULL or lacks an "npcs" key are skipped safely
    # because jsonb_each returns 0 rows for NULL/missing paths.
    op.execute(
        """
        UPDATE campaigns
        SET world_state = jsonb_set(
            world_state,
            '{npcs}',
            (
                SELECT jsonb_object_agg(
                    npc_entry.npc_name,
                    CASE
                        WHEN (npc_entry.npc_data ? 'disposition')
                             AND NOT (npc_entry.npc_data ? 'disposition_toward_player')
                        THEN
                            (npc_entry.npc_data - 'disposition')
                            || jsonb_build_object(
                                'disposition_toward_player',
                                (npc_entry.npc_data->>'disposition')::int
                               )
                        ELSE
                            npc_entry.npc_data
                    END
                )
                FROM jsonb_each(world_state->'npcs') AS npc_entry(npc_name, npc_data)
            ),
            true
        )
        WHERE
            world_state IS NOT NULL
            AND world_state ? 'npcs'
            AND EXISTS (
                SELECT 1
                FROM jsonb_each(world_state->'npcs') AS e(k, v)
                WHERE (v ? 'disposition') AND NOT (v ? 'disposition_toward_player')
            )
        """
    )


def downgrade() -> None:
    # Rename disposition_toward_player back to disposition (best-effort).
    op.execute(
        """
        UPDATE campaigns
        SET world_state = jsonb_set(
            world_state,
            '{npcs}',
            (
                SELECT jsonb_object_agg(
                    npc_entry.npc_name,
                    CASE
                        WHEN npc_entry.npc_data ? 'disposition_toward_player'
                        THEN
                            (npc_entry.npc_data - 'disposition_toward_player')
                            || jsonb_build_object(
                                'disposition',
                                (npc_entry.npc_data->>'disposition_toward_player')::int
                               )
                        ELSE
                            npc_entry.npc_data
                    END
                )
                FROM jsonb_each(world_state->'npcs') AS npc_entry(npc_name, npc_data)
            ),
            true
        )
        WHERE
            world_state IS NOT NULL
            AND world_state ? 'npcs'
            AND EXISTS (
                SELECT 1
                FROM jsonb_each(world_state->'npcs') AS e(k, v)
                WHERE v ? 'disposition_toward_player'
            )
        """
    )
