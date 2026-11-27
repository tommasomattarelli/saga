from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.npc_resolver import npcs_at_current_location
from app.core.world_access import WorldView
from app.memory.context_snapshot import HistoryMessage


def build_gazetteer(
    world_state: dict, world_baseline: dict, known_names: Sequence[str] = ()
) -> tuple[str, ...]:
    names = set(known_names)
    for npc in world_state.get("npcs", {}).values():
        for key in ("name", "slug"):
            if npc.get(key):
                names.add(npc[key])
    for node in world_baseline.get("nodes", {}).values():
        if node.get("name"):
            names.add(node["name"])
    return tuple(sorted(names))


def _expansion_names(world_state: dict) -> set[str]:
    npcs = world_state.get("npcs", {}).values()
    present = npcs_at_current_location(world_state).values()
    candidates = [npc for npc in present]
    candidates.extend(npc for npc in npcs if npc.get("met_player") or npc.get("last_interactions"))
    return {npc["name"] for npc in candidates if npc.get("name")}


def _last_mentioned(
    history: Sequence[HistoryMessage], matching_names: Sequence[str], recent_turns: int
) -> str | None:
    tail = history[-recent_turns * 2 :]
    ordered = sorted(matching_names, key=len, reverse=True)
    for message in reversed(tail):
        for name in ordered:
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", message.content, re.IGNORECASE):
                return name
    return None


def build_scene_anchor(
    world_state: dict,
    world_baseline: dict,
    history: Sequence[HistoryMessage],
    known_names: Sequence[str] = (),
    *,
    include_scene: bool = True,
    recent_turns: int = 2,
    max_chars: int = 200,
) -> str:
    if not include_scene:
        return ""
    view = WorldView(world_baseline, world_state)
    position = view.player_position()
    location = None
    if position:
        node = view.node(position)
        location = node.get("name") if node else None
    if not location:
        location = world_state.get("meta", {}).get("current_location")

    names = sorted(_expansion_names(world_state))
    mentioned = _last_mentioned(
        history, build_gazetteer(world_state, world_baseline, known_names), recent_turns
    )
    if mentioned and mentioned not in names:
        names.append(mentioned)

    parts: list[str] = []
    if location:
        parts.append(f"At {location}")
    if names:
        parts.append("with " + " and ".join(names))
    anchor = (", ".join(parts) + ".") if parts else ""
    return anchor[:max_chars]


async def build_lexical_query(db: AsyncSession, action: str, matching_names: Sequence[str]) -> str:
    rows = (
        (
            await db.execute(
                text(
                    "SELECT lexeme FROM unnest(to_tsvector('simple', :action)) "
                    "WHERE length(lexeme) >= 2"
                ),
                {"action": action},
            )
        )
        .scalars()
        .all()
    )
    lowered = {name.lower() for name in matching_names}
    tokens = [
        f"{lexeme}:*" if lexeme.lower() in lowered else lexeme for lexeme in dict.fromkeys(rows)
    ]
    return " | ".join(tokens)
