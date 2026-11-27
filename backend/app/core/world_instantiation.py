"""ADR 0008 — World asset → campaign save (A6/D7/C8/C11/J3).

Assigns runtime UUIDs (slugs never enter the save's reference graph),
composes global km positions (A7), builds the alias index (F13), and seeds
the initial overlay (`world_state`) + quests from `scenario.yaml`.
"""

from uuid import uuid4

import structlog

from app.core.npc_classes import DEFAULT_NPC_CLASSES, draw_statblock, statblock_defaults
from app.core.npc_fields import DEFAULT_NPC_FIELDS, default_traits
from app.core.psychology import DEFAULT_PSYCHOLOGY, default_values
from app.core.relations import relation_kind_default, relation_kind_defaults
from app.core.world_loader import WorldAsset
from app.memory.world_state import CURRENT_SCHEMA_VERSION, GameClock
from app.models.npc import NpcEngineRecord
from app.models.quest import QuestRecord, QuestRegistry

logger = structlog.get_logger()


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


def _seed_relations(asset: WorldAsset, npcs: dict[str, dict]) -> list[dict]:
    kinds = relation_kind_defaults(asset.taxonomy.model_dump())
    edges: list[dict] = []

    def add(src: dict, dst: dict, kind: str, stance: int, label: str, prominent: bool | None):
        default, candidates = relation_kind_default(kind, kinds)
        if default is None:
            logger.warning("authored_relation_kind_dropped", kind=kind, candidates=candidates)
            return
        edges.append(
            {
                "src": src,
                "dst": dst,
                "kind": kind,
                "stance": stance,
                "label": label,
                "prominent": default if prominent is None else prominent,
                "since_turn": 0,
                "since_game_minutes": 480,
            }
        )

    by_slug = {npc["slug"]: npc_id for npc_id, npc in npcs.items()}
    for faction in asset.factions.values():
        for target_slug, relation in faction.relations.items():
            if target_slug not in asset.factions:
                logger.warning("authored_relation_target_dropped", target=target_slug)
                continue
            add(
                {"type": "faction", "id": faction.slug},
                {"type": "faction", "id": target_slug},
                "faction",
                relation.stance * 10,
                relation.label,
                None,
            )
        if faction.reputation_tiers:
            band = max(
                (t for t in faction.reputation_tiers if t.threshold <= 0),
                key=lambda t: t.threshold,
                default=min(faction.reputation_tiers, key=lambda t: t.threshold),
            )
            add(
                {"type": "faction", "id": faction.slug},
                {"type": "player", "id": None},
                "reputation",
                0,
                band.label,
                None,
            )
    for authored in asset.npcs.values():
        src_id = by_slug.get(authored.slug)
        if src_id is None:
            continue
        for authored_relation in authored.relations:
            if authored_relation.target == "player":
                dst = {"type": "player", "id": None}
            elif authored_relation.target in by_slug:
                dst = {"type": "npc", "id": by_slug[authored_relation.target]}
            elif authored_relation.target in asset.factions:
                dst = {"type": "faction", "id": authored_relation.target}
            else:
                logger.warning("authored_relation_target_dropped", target=authored_relation.target)
                continue
            add(
                {"type": "npc", "id": src_id},
                dst,
                authored_relation.kind,
                authored_relation.stance,
                authored_relation.label,
                authored_relation.prominent,
            )
    return edges


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
        # Dumped, not a literal: advance_game_clock writes the computed fields too, and a
        # campaign that has not moved yet must not read differently from one that has.
        "clock": GameClock(total_minutes=480).model_dump(),
        "npcs": npcs,
        "companions": {},
        "factions": {
            f.slug: {"name": f.name, "description": f.description} for f in asset.factions.values()
        },
        "relations": _seed_relations(asset, npcs),
        "narrative": {"event_log": []},
        "fate_interventions_left": 3,
        "time_of_day": (opening.time_of_day if opening else "") or "morning",
        "weather": (opening.weather if opening else "") or "clear",
        "node_status": {},
        "edge_overrides": [],
        "consumed_encounters": {},
    }


def instantiate_world(asset: WorldAsset) -> tuple[dict, dict, dict]:
    """Returns (world_baseline, initial world_state, initial quest registry)."""
    slug_map = {slug: str(uuid4()) for slug in asset.nodes}
    baseline = _build_baseline(asset, slug_map)
    world_state = _build_world_state(asset, slug_map)
    active = (
        [QuestRecord.model_validate(q.model_dump()) for q in asset.scenario.initial_quests]
        if asset.scenario
        else []
    )
    return baseline, world_state, QuestRegistry(active=active).model_dump()
