"""<scene> location block from the hierarchical world (ADR 0008 J1/J4).

Spine-only by default: ancestor names, current node in full, immediate exits
and travel options — capped by the `world.scene` knobs in saga.config.yaml.
"""

from app.config_loader import load_saga_config
from app.core.travel import TravelConfig, _edge_minutes
from app.core.world_access import WorldView


def _scene_knobs() -> dict:
    world_cfg = load_saga_config().get("world") or {}
    return {
        "max_breadcrumb_depth": 4,
        "show_travel_options": True,
        "max_travel_options": 6,
        "include_node_status": True,
        "description_max_chars": 600,
        "scene_context_max_tokens": 700,
        **(world_cfg.get("scene") or {}),
    }


def _travel_config() -> TravelConfig:
    travel_cfg = (load_saga_config().get("world") or {}).get("travel") or {}
    return TravelConfig(
        elevation_coeff=float(travel_cfg.get("elevation_coeff", 7.92)),
        local_move_minutes=int(travel_cfg.get("local_move_minutes", 5)),
    )


def _travel_options(view: WorldView, position: str, knobs: dict) -> list[str]:
    config = _travel_config()
    options = []
    for edge in view.edges().values():
        if edge["from"] == position:
            other = edge["to"]
        elif edge["to"] == position and not edge.get("directed"):
            other = edge["from"]
        else:
            continue
        node = view.node(other)
        if node is None:
            continue
        minutes = round(_edge_minutes(edge, view, config))
        options.append(f"{node['name']} — {edge['mode']}, ~{minutes} min")
        if len(options) >= int(knobs["max_travel_options"]):
            break
    return options


def render_location_block(view: WorldView, position: str) -> list[str]:
    """Lines for the <location> block; caller wraps them in <scene>."""
    knobs = _scene_knobs()
    node = view.node(position)
    if node is None:
        return []

    crumbs = view.breadcrumb(position)[:-1]
    depth = int(knobs["max_breadcrumb_depth"])
    spine = " > ".join(crumbs[-depth:]) if crumbs else ""

    lines: list[str] = []
    path_attr = f' path="{spine}"' if spine else ""
    lines.append(f'  <location name="{node["name"]}"{path_attr}>')

    description = (node.get("description") or "").strip()
    max_chars = int(knobs["description_max_chars"])
    if description:
        lines.append(f"    {description[:max_chars]}")

    if knobs["include_node_status"] and node.get("status"):
        status = node["status"]
        status_text = status.get("description") or status.get("status", "")
        lines.append(f"    <status>{status.get('status', '')}: {status_text}</status>")

    if view.scale(position) == "interior":
        exits = [e["to"] for e in (node.get("exits") or []) if not e.get("hidden")]
        if exits:
            names = []
            for target in exits:
                target_id = view.id_of(target)
                names.append(view.require(target_id)["name"] if target_id else target)
            lines.append(f"    <exits>{', '.join(names)}</exits>")
        parent = view.parent_of(position)
        if parent:
            lines.append(f"    <outside>{view.require(parent)['name']}</outside>")
    else:
        interior_children = [
            view.require(c)["name"]
            for c in view._baseline["nodes"][position].get("children", [])
            if view.scale(c) == "interior"
        ]
        if interior_children:
            lines.append(f"    <places_inside>{', '.join(interior_children)}</places_inside>")
        if knobs["show_travel_options"]:
            options = _travel_options(view, position, knobs)
            if options:
                lines.append("    <travel_options>")
                lines.extend(f"      {o}" for o in options)
                lines.append("    </travel_options>")

    lines.append("  </location>")

    # Hard token cap (~4 chars/token): truncate from the tail, keep the closing tag.
    max_chars_total = int(knobs["scene_context_max_tokens"]) * 4
    if sum(len(line) for line in lines) > max_chars_total:
        kept: list[str] = []
        used = 0
        for line in lines[:-1]:
            if used + len(line) > max_chars_total:
                break
            kept.append(line)
            used += len(line)
        lines = [*kept, "  </location>"]
    return lines
