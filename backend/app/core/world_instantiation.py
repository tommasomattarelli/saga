"""ADR 0008 — World asset → campaign save (A6/D7/C8/C11/J3).

Assigns runtime UUIDs (slugs never enter the save's reference graph),
composes global km positions (A7), builds the alias index (F13), and seeds
the initial overlay (`world_state`) + quests from `scenario.yaml`.
"""

from uuid import uuid4

from app.core.npc_classes import DEFAULT_NPC_CLASSES, draw_statblock, statblock_defaults
from app.core.npc_fields import DEFAULT_NPC_FIELDS, default_traits
from app.core.psychology import DEFAULT_PSYCHOLOGY, default_values
from app.core.world_loader import WorldAsset
from app.memory.world_state import CURRENT_SCHEMA_VERSION
from app.models.npc import NpcEngineRecord


def _global_km(asset: WorldAsset, slug: str, cache: dict[str, dict | None]) -> dict | None:
    if slug in cache:
        return cache[slug]
    node = asset.nodes[slug]
    kind = asset.taxonomy.kind(node.kind)
    if kind is None or kind.scale == "interior" or node.position is None:
        cache[slug] = None
        return None
    parent_slug = asset.parent[slug]
    if parent_slug is None:
        result = {"x": float(node.position.x), "y": float(node.position.y)}
    else:
        parent_global = _global_km(asset, parent_slug, cache)
        if parent_global is None:
            result = None
        else:
            k = asset.nodes[parent_slug].km_per_unit
            result = {
                "x": parent_global["x"] + node.position.x * k,
                "y": parent_global["y"] + node.position.y * k,
            }
    cache[slug] = result
    return result


def _build_baseline(asset: WorldAsset, slug_map: dict[str, str]) -> dict:
    km_cache: dict[str, dict | None] = {}
    nodes: dict[str, dict] = {}
    for slug, node in asset.nodes.items():
        kind = asset.taxonomy.kind(node.kind)
        parent_slug = asset.parent[slug]
        nodes[slug_map[slug]] = {
            **node.model_dump(),
            "parent": slug_map[parent_slug] if parent_slug else None,
            "children": [],
            "scale": kind.scale if kind else "outdoor",
            "global_km": _global_km(asset, slug, km_cache),
        }
    for node_id, dumped_node in nodes.items():
        if dumped_node["parent"] is not None:
            nodes[dumped_node["parent"]]["children"].append(node_id)

    alias: dict[str, list[str]] = {}
    for slug, world_node in asset.nodes.items():
        for key in {slug, world_node.name.lower()}:
            alias.setdefault(key, []).append(slug_map[slug])

    edges = {}
    for slug, edge in asset.edges.items():
        dumped = edge.model_dump(by_alias=True)
        dumped["from"] = slug_map[edge.from_]
        dumped["to"] = slug_map[edge.to]
        edges[slug] = dumped

    return {
        "source_world": asset.root_slug,
        "world_version": asset.meta.version,
        "root": slug_map[asset.root_slug],
        "nodes": nodes,
        "edges": edges,
        "taxonomy": asset.taxonomy.model_dump(),
        "factions": {slug: f.model_dump() for slug, f in asset.factions.items()},
        "encounters": {slug: e.model_dump() for slug, e in asset.encounters.items()},
        "alias": alias,
        "slug_map": slug_map,
    }


def _build_world_state(asset: WorldAsset, slug_map: dict[str, str]) -> dict:
    opening = asset.scenario.opening if asset.scenario else None
    start_id = slug_map[opening.start_location] if opening else slug_map[asset.root_slug]
    axis_defaults = default_values(asset.taxonomy.psychology or DEFAULT_PSYCHOLOGY)
    trait_defaults = default_traits(asset.taxonomy.npc_fields or DEFAULT_NPC_FIELDS)
    # ADR 0009 F1: runtime UUID keys — authored slugs become resolution aliases.
    npc_classes = asset.taxonomy.npc_classes or DEFAULT_NPC_CLASSES
    npcs: dict[str, dict] = {
        str(uuid4()): NpcEngineRecord(
            slug=npc.slug,
            name=npc.name,
            location=slug_map[npc.location] if npc.location else None,
            faction=npc.faction,
            # Authored seeds are baseline prejudice — they never flip met_player (B3).
            psychology={**axis_defaults, **npc.psychology},
            traits={**trait_defaults, **npc.descriptives()},
            # ADR 0003 B3 — authored statblock wins, the class template fills the rest.
            **draw_statblock(
                npc.npc_class or statblock_defaults()["npc_class"],
                npc_classes,
                authored=npc.statblock(),
            ),
        ).model_dump()
        for npc in asset.npcs.values()
    }
    return {
        "meta": {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "world_name": asset.meta.name,
            "setting": asset.nodes[asset.root_slug].description,
            "current_location": start_id,
            "current_season": "spring",
            "opening_narration": opening.narration if opening else "",
        },
        "player_position": start_id,
        "clock": {"total_minutes": 480},
        "npcs": npcs,
        "companions": {},
        "factions": {
            f.name: {"description": f.description, "disposition": 0}
            for f in asset.factions.values()
        },
        "narrative": {"event_log": []},
        "destino_lives": 3,
        "time_of_day": (opening.time_of_day if opening else "") or "morning",
        "weather": (opening.weather if opening else "") or "clear",
        "node_status": {},
        "edge_overrides": [],
        "consumed_encounters": {},
    }


def instantiate_world(asset: WorldAsset) -> tuple[dict, dict, dict]:
    """Returns (world_baseline, initial world_state, initial quests)."""
    slug_map = {slug: str(uuid4()) for slug in asset.nodes}
    baseline = _build_baseline(asset, slug_map)
    world_state = _build_world_state(asset, slug_map)
    quests = (
        {"active": [q.model_dump() for q in asset.scenario.initial_quests]}
        if asset.scenario and asset.scenario.initial_quests
        else {}
    )
    return baseline, world_state, quests
