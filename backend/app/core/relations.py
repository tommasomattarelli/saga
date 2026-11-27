from __future__ import annotations

from app.memory.graph_config import get_graph_config


def relation_kind_defaults(taxonomy: dict) -> dict[str, bool]:
    kinds = {kind.kind: kind.prominent for kind in get_graph_config().default_relation_kinds}
    kinds.update(
        {entry["kind"]: entry["prominent"] for entry in taxonomy.get("relation_kinds", [])}
    )
    return kinds


def relation_kind_default(kind: str, kinds: dict[str, bool]) -> tuple[bool | None, list[str]]:
    if kind in kinds:
        return kinds[kind], []
    return None, sorted(kinds)


def relation_kind_descriptions(taxonomy: dict) -> dict[str, str]:
    descriptions = {
        kind.kind: kind.description
        for kind in get_graph_config().default_relation_kinds
        if kind.description
    }
    descriptions.update(
        {
            entry["kind"]: entry["description"]
            for entry in taxonomy.get("relation_kinds", [])
            if entry.get("description")
        }
    )
    return descriptions


def upsert_relation_edge(
    edges: list[dict], edge: dict, max_edges: int | None = None
) -> bool | None:
    """Update an open triple; True appended, False updated, None capped."""
    for existing in edges:
        if (
            existing["src"] == edge["src"]
            and existing["dst"] == edge["dst"]
            and existing["kind"] == edge["kind"]
            and existing.get("until_turn") is None
        ):
            existing.update(
                stance=edge["stance"], label=edge["label"], prominent=edge["prominent"]
            )
            return False
    if max_edges is not None and len(edges) >= max_edges:
        return None
    edges.append(edge)
    return True


def resolve_faction_slug(name: str, world_state: dict) -> tuple[str | None, str, list[str]]:
    factions = world_state.get("factions", {})
    wanted = name.strip().casefold()
    slug_matches = [slug for slug in factions if slug.casefold() == wanted]
    display_matches = [
        slug
        for slug, faction in factions.items()
        if str(faction.get("name", "")).strip().casefold() == wanted
    ]
    pool = slug_matches or display_matches
    if len(pool) == 1:
        return pool[0], "", []
    if len(pool) > 1:
        return None, f"Multiple factions match '{name}' — specify which one.", sorted(pool)
    return None, f"{name} is not a known faction.", sorted(factions)
