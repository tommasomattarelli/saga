"""ADR 0008 — travel engine: route graph, Naismith time, encounters (F8/F11–F13).

`attempt_move` is pure: it computes an outcome without touching the overlay.
The move_to tool applies the outcome (position, clock, consumed encounters).
"""

import math
import random
import re
from dataclasses import dataclass, field

import networkx as nx

from app.core.world_access import WorldView

_DICE_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")


@dataclass
class TravelConfig:
    elevation_coeff: float = 7.92
    local_move_minutes: int = 5


@dataclass
class MoveOutcome:
    ok: bool
    reason: str = ""
    destination: str | None = None
    minutes: int = 0
    local: bool = False
    encounter: dict | None = None
    consumed_key: str = ""
    candidates: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)


def _edge_minutes(edge: dict, view: WorldView, config: TravelConfig) -> float:
    if edge.get("travel_time"):
        return float(edge["travel_time"]) * 60
    speed = view.mode_speed(edge["mode"]) or 4.0
    distance_km = edge.get("distance_km")
    if distance_km is None:
        a = view.node(edge["from"])
        b = view.node(edge["to"])
        ga, gb = (a or {}).get("global_km"), (b or {}).get("global_km")
        if not ga or not gb:
            return config.local_move_minutes
        distance_km = math.dist((ga["x"], ga["y"]), (gb["x"], gb["y"]))
    climb_m = max(
        0.0,
        float((view.node(edge["to"]) or {}).get("elevation_m") or 0)
        - float((view.node(edge["from"]) or {}).get("elevation_m") or 0),
    )
    equiv_km = distance_km + config.elevation_coeff * climb_m / 1000
    hours = equiv_km / speed * view.terrain_multiplier(edge.get("terrain"))
    return hours * 60


def _build_graph(view: WorldView, config: TravelConfig) -> nx.DiGraph:
    graph = nx.DiGraph()
    baseline_nodes = view._baseline.get("nodes", {})
    graph.add_nodes_from(baseline_nodes)
    slug_map = view._baseline.get("slug_map", {})

    # Interior connectivity: authored exits win; a node without exits gets an
    # implicit containment link to its parent (doors exist both ways, F10).
    for node_id, node in baseline_nodes.items():
        if node.get("scale") != "interior":
            continue
        parent = node.get("parent")
        exits = node.get("exits") or []
        if not exits:
            if parent is not None:
                graph.add_edge(node_id, parent, minutes=config.local_move_minutes, local=True)
                graph.add_edge(parent, node_id, minutes=config.local_move_minutes, local=True)
            continue
        for exit_ in exits:
            if exit_.get("locked"):
                continue
            target = parent if exit_["to"] == "outside" else slug_map.get(exit_["to"])
            if target is None:
                continue
            graph.add_edge(node_id, target, minutes=config.local_move_minutes, local=True)
            graph.add_edge(target, node_id, minutes=config.local_move_minutes, local=True)

    # Outdoor travel: the authored route graph is the source of truth (F3).
    for slug, edge in view.edges().items():
        minutes = _edge_minutes(edge, view, config)
        graph.add_edge(edge["from"], edge["to"], minutes=minutes, local=False, edge_slug=slug)
        if not edge.get("directed"):
            graph.add_edge(edge["to"], edge["from"], minutes=minutes, local=False, edge_slug=slug)
    return graph


def _roll(dice: str, rng) -> int:
    match = _DICE_RE.match(dice)
    if not match:
        return 0
    count, sides = int(match.group(1)), int(match.group(2))
    bonus = int(match.group(3) or 0)
    return sum(rng.randint(1, sides) for _ in range(count)) + bonus


def _check_encounters(
    view: WorldView, hops: list[tuple[str, str]], graph, rng
) -> tuple[dict | None, str]:
    edges = view.edges()
    consumed = view._overlay.get("consumed_encounters", {})
    for u, v in hops:
        data = graph.get_edge_data(u, v) or {}
        slug = data.get("edge_slug")
        if not slug:
            continue
        edge = edges.get(slug, {})
        table_slug = edge.get("encounter_table")
        chance = edge.get("encounter_chance")
        if not table_slug or not chance:
            continue
        if rng.random() >= chance:
            continue
        table = view._baseline.get("encounters", {}).get(table_slug)
        if not table:
            continue
        roll = _roll(table["dice"], rng)
        for index, entry in enumerate(table["entries"]):
            low, high = entry["roll"]
            if low <= roll <= high:
                if entry.get("once") and index in consumed.get(slug, []):
                    break  # already lived through it — quiet road
                return {**entry, "index": index}, slug
        break  # one encounter check resolves the whole montage (F1)
    return None, ""


def attempt_move(
    view: WorldView, target_query: str, config: TravelConfig, rng=None
) -> MoveOutcome:
    rng = rng or random
    current = view.player_position()
    if current is None or not view.has_world:
        return MoveOutcome(ok=False, reason="No world position — the world has no baseline.")

    result = view.resolve(target_query, current)
    if result.candidates:
        names = [" > ".join(view.breadcrumb(c)) for c in result.candidates]
        return MoveOutcome(
            ok=False,
            reason=f"Ambiguous destination '{target_query}'. Candidates: {'; '.join(names)}. Re-call move_to with the full name.",
            candidates=result.candidates,
        )
    if result.match is None:
        return MoveOutcome(ok=False, reason=f"Unknown place '{target_query}'.")
    if result.match == current:
        return MoveOutcome(ok=False, reason=f"Already at {view.require(current)['name']}.")

    graph = _build_graph(view, config)
    try:
        path = nx.shortest_path(graph, current, result.match, weight="minutes")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return MoveOutcome(
            ok=False,
            reason=f"No route from {view.require(current)['name']} to {view.require(result.match)['name']} — no path exists (missing road, sea in between, or a locked way).",
        )

    hops = list(zip(path, path[1:], strict=False))
    minutes = round(sum(graph[u][v]["minutes"] for u, v in hops))
    local = all(graph[u][v].get("local") for u, v in hops)
    encounter, consumed_key = (None, "") if local else _check_encounters(view, hops, graph, rng)

    return MoveOutcome(
        ok=True,
        destination=result.match,
        minutes=minutes,
        local=local,
        encounter=encounter,
        consumed_key=consumed_key,
        path=[view.require(p)["name"] for p in path],
    )
