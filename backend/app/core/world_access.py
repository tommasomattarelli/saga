"""ADR 0008 — WorldView: the single merge accessor over baseline + overlay (C11).

Every reader of the hierarchical world goes through this module. Nobody
merges `world_baseline` and `world_state` by hand — three divergent read
conventions caused the ability-score bug; never again.
"""

import copy
from dataclasses import dataclass, field


@dataclass
class ResolveResult:
    match: str | None = None
    candidates: list[str] = field(default_factory=list)


class WorldView:
    def __init__(self, baseline: dict, overlay: dict):
        self._baseline = baseline
        self._overlay = overlay

    @property
    def has_world(self) -> bool:
        return bool(self._baseline.get("nodes"))

    def id_of(self, slug: str) -> str | None:
        return self._baseline.get("slug_map", {}).get(slug)

    def node(self, node_id: str) -> dict | None:
        raw = self._baseline.get("nodes", {}).get(node_id)
        if raw is None:
            return None
        node = copy.deepcopy(raw)
        status = self._overlay.get("node_status", {}).get(node_id)
        node["status"] = status
        if status:
            for param, delta in (status.get("modifiers") or {}).items():
                if param in node.get("params", {}):
                    node["params"][param] += delta
        return node

    def require(self, node_id: str) -> dict:
        node = self.node(node_id)
        if node is None:
            raise KeyError(f"unknown world node '{node_id}'")
        return node

    def scale(self, node_id: str) -> str:
        return self._baseline["nodes"][node_id].get("scale", "outdoor")

    def parent_of(self, node_id: str) -> str | None:
        return self._baseline["nodes"][node_id].get("parent")

    def ancestors(self, node_id: str) -> list[str]:
        """Chain from the root down to (excluding) the node."""
        chain: list[str] = []
        cursor = self.parent_of(node_id)
        while cursor is not None:
            chain.append(cursor)
            cursor = self.parent_of(cursor)
        chain.reverse()
        return chain

    def breadcrumb(self, node_id: str) -> list[str]:
        nodes = self._baseline["nodes"]
        return [nodes[a]["name"] for a in self.ancestors(node_id)] + [nodes[node_id]["name"]]

    def player_position(self) -> str | None:
        return self._overlay.get("player_position")

    def edges(self) -> dict[str, dict]:
        """Baseline edges with overlay `edge_overrides` applied (G3b)."""
        edges = copy.deepcopy(self._baseline.get("edges", {}))
        for override in self._overlay.get("edge_overrides", []):
            op, slug = override.get("op"), override.get("edge")
            if op == "remove":
                edges.pop(slug, None)
            elif op == "add":
                edges[slug] = override.get("data", {})
            elif op == "modify" and slug in edges:
                edges[slug].update(override.get("data", {}))
        return edges

    def _lca_depth(self, a: str, b: str) -> int:
        chain_a = [*self.ancestors(a), a]
        chain_b = [*self.ancestors(b), b]
        depth = -1
        for i, (x, y) in enumerate(zip(chain_a, chain_b, strict=False)):
            if x != y:
                break
            depth = i
        return depth

    def resolve(self, query: str, current: str | None = None) -> ResolveResult:
        """Scoped name/slug resolution (F7/F13): nearest scope wins, ties reject."""
        candidates = list(dict.fromkeys(self._baseline.get("alias", {}).get(query.lower(), [])))
        if not candidates:
            return ResolveResult()
        if len(candidates) == 1:
            return ResolveResult(match=candidates[0])
        current = current or self.player_position()
        if current is None:
            return ResolveResult(candidates=candidates)
        scored = sorted(candidates, key=lambda c: self._lca_depth(c, current), reverse=True)
        best = self._lca_depth(scored[0], current)
        tied = [c for c in scored if self._lca_depth(c, current) == best]
        if len(tied) == 1:
            return ResolveResult(match=tied[0])
        return ResolveResult(candidates=tied)

    def taxonomy(self) -> dict:
        return self._baseline.get("taxonomy", {})

    def terrain_multiplier(self, name: str | None) -> float:
        taxonomy = self.taxonomy()
        target = name or (taxonomy.get("defaults") or {}).get("terrain")
        for terrain in taxonomy.get("terrains", []):
            if terrain["name"] == target:
                return float(terrain["travel_multiplier"])
        return 1.0

    def mode_speed(self, name: str) -> float | None:
        for mode in self.taxonomy().get("travel_modes", []):
            if mode["name"] == name:
                return float(mode["speed_kmh"])
        return None
