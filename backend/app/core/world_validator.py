"""ADR 0008 — tier-3 referential integrity + dynamic param validation (I4/E2).

Operates on a loaded `WorldAsset`; returns a flat list of human-readable
errors (empty = valid). Structural rules, cross-file references, and the
per-kind param contract the static models cannot check.
"""

from app.core.psychology import DEFAULT_PSYCHOLOGY
from app.core.world_loader import WorldAsset
from app.models.world import KindDef, ParamDef, ParamValue, WorldNode

_PARAM_TYPES: dict[str, type | tuple[type, ...]] = {
    "int": int,
    "float": (int, float),
    "str": str,
    "bool": bool,
}


def _check_param(node_slug: str, definition: ParamDef, value: ParamValue) -> list[str]:
    expected = _PARAM_TYPES[definition.type]
    if isinstance(value, bool) and definition.type != "bool":
        return [f"{node_slug}: param '{definition.name}' must be {definition.type}"]
    if not isinstance(value, expected):
        return [f"{node_slug}: param '{definition.name}' must be {definition.type}"]
    errors = []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if definition.min is not None and value < definition.min:
            errors.append(f"{node_slug}: param '{definition.name}' below min {definition.min}")
        if definition.max is not None and value > definition.max:
            errors.append(f"{node_slug}: param '{definition.name}' above max {definition.max}")
    return errors


def _check_params(node: WorldNode, kind: KindDef) -> list[str]:
    errors = []
    defs = {p.name: p for p in kind.params}
    for name in node.params:
        if name not in defs:
            errors.append(f"{node.slug}: param '{name}' not declared for kind '{kind.name}'")
    for definition in kind.params:
        if definition.name in node.params:
            errors += _check_param(node.slug, definition, node.params[definition.name])
        elif definition.required:
            errors.append(f"{node.slug}: required param '{definition.name}' missing")
    return errors


def _check_node(asset: WorldAsset, node: WorldNode) -> list[str]:
    kind = asset.taxonomy.kind(node.kind)
    if kind is None:
        return [f"{node.slug}: unknown kind '{node.kind}'"]
    errors = []
    if kind.scale == "outdoor" and node.position is None:
        errors.append(f"{node.slug}: outdoor node requires a position")
    if kind.scale == "interior" and node.position is not None:
        errors.append(f"{node.slug}: interior node must not have a position")
    if node.terrain is not None and asset.taxonomy.terrain(node.terrain) is None:
        errors.append(f"{node.slug}: unknown terrain '{node.terrain}'")
    parent_slug = asset.parent[node.slug]
    if parent_slug is not None:
        parent_kind = asset.taxonomy.kind(asset.nodes[parent_slug].kind)
        if parent_kind and parent_kind.scale == "interior" and kind.scale == "outdoor":
            errors.append(f"{node.slug}: outdoor node cannot live inside interior '{parent_slug}'")
    for exit_ in node.exits:
        if exit_.to != "outside" and exit_.to not in asset.nodes:
            errors.append(f"{node.slug}: exit target '{exit_.to}' does not exist")
    errors += _check_params(node, kind)
    return errors


def _check_depth(asset: WorldAsset, max_depth: int) -> list[str]:
    errors = []
    for slug in asset.nodes:
        depth, cursor = 0, asset.parent[slug]
        while cursor is not None:
            depth += 1
            cursor = asset.parent[cursor]
        if depth > max_depth:
            errors.append(f"{slug}: depth {depth} exceeds max_depth {max_depth}")
    return errors


def _check_edges(asset: WorldAsset) -> list[str]:
    errors = []
    for edge in asset.edges.values():
        for endpoint in (edge.from_, edge.to):
            if endpoint not in asset.nodes:
                errors.append(f"edge {edge.slug}: endpoint '{endpoint}' does not exist")
        if asset.taxonomy.mode(edge.mode) is None:
            errors.append(f"edge {edge.slug}: unknown travel mode '{edge.mode}'")
        if edge.terrain is not None and asset.taxonomy.terrain(edge.terrain) is None:
            errors.append(f"edge {edge.slug}: unknown terrain '{edge.terrain}'")
        if edge.encounter_table is not None and edge.encounter_table not in asset.encounters:
            errors.append(f"edge {edge.slug}: unknown encounter table '{edge.encounter_table}'")
    return errors


def _check_references(asset: WorldAsset) -> list[str]:
    errors = []
    psychology = asset.taxonomy.psychology or DEFAULT_PSYCHOLOGY
    for npc in asset.npcs.values():
        if npc.location is not None and npc.location not in asset.nodes:
            errors.append(f"npc {npc.slug}: location '{npc.location}' does not exist")
        if npc.faction is not None and npc.faction not in asset.factions:
            errors.append(f"npc {npc.slug}: faction '{npc.faction}' does not exist")
        for axis_name, value in npc.psychology.items():
            axis = psychology.axes.get(axis_name)
            if axis is None:
                errors.append(f"npc {npc.slug}: unknown psychology axis '{axis_name}'")
            elif not axis.range[0] <= value <= axis.range[1]:
                errors.append(
                    f"npc {npc.slug}: psychology '{axis_name}' value {value} "
                    f"outside range {list(axis.range)}"
                )
    for faction in asset.factions.values():
        for other in faction.relations:
            if other not in asset.factions:
                errors.append(f"faction {faction.slug}: relation target '{other}' does not exist")
    if asset.scenario is not None:
        start = asset.scenario.opening.start_location
        if start not in asset.nodes:
            errors.append(f"scenario: start_location '{start}' does not exist")
    return errors


def validate_world(asset: WorldAsset, max_depth: int) -> list[str]:
    errors: list[str] = []
    for node in asset.nodes.values():
        errors += _check_node(asset, node)
    errors += _check_depth(asset, max_depth)
    errors += _check_edges(asset)
    errors += _check_references(asset)
    return errors
