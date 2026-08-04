"""ADR 0008 — editable payload ⇄ authored YAML tree (I6/I7).

`to_editable` flattens a loaded WorldAsset into the slug-based JSON the
editor consumes; `write_world` serializes that payload back into the
directory-convention layout (D3/D5). Slugs live in filenames only (D3c).
"""

from pathlib import Path

import yaml

from app.core.world_loader import WorldAsset


def _clean(data: dict) -> dict:
    """Drop empty/None fields so files stay as lean as hand-authored ones."""
    return {
        k: v
        for k, v in data.items()
        if v is not None and v != [] and v != {} and not (k == "km_per_unit" and v == 1.0)
    }


def to_editable(asset: WorldAsset) -> dict:
    root = asset.nodes[asset.root_slug]
    nodes = []
    for slug, node in asset.nodes.items():
        if slug == asset.root_slug:
            continue
        dumped = node.model_dump(exclude={"slug"}, exclude_none=True)
        nodes.append({"slug": slug, "parent": asset.parent[slug], **_clean(dumped)})
    nodes.sort(key=lambda n: str(n["slug"]))

    def collection(items: dict, by_alias: bool = False) -> list[dict]:
        out = []
        for slug, item in sorted(items.items()):
            dumped = item.model_dump(exclude={"slug"}, exclude_none=True, by_alias=by_alias)
            out.append({"slug": slug, **_clean(dumped)})
        return out

    return {
        "meta": asset.meta.model_dump(),
        "root": _clean(
            {
                "kind": root.kind,
                "description": root.description,
                "km_per_unit": root.km_per_unit,
                "elevation_m": root.elevation_m,
                "terrain": root.terrain,
                "map_image": root.map_image,
                "params": root.params,
                "items": [i.model_dump(exclude_none=True) for i in root.items],
            }
        ),
        # mode="json" unwraps StrEnum members (npc_class fields): SafeDumper refuses them.
        "taxonomy": asset.taxonomy.model_dump(mode="json"),
        "scenario": asset.scenario.model_dump(exclude_none=True) if asset.scenario else None,
        "nodes": nodes,
        "edges": collection(asset.edges, by_alias=True),
        "factions": collection(asset.factions),
        "npcs": collection(asset.npcs),
        "encounters": collection(asset.encounters),
    }


def _dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(_clean(data), allow_unicode=True, sort_keys=False))


def write_world(payload: dict, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)

    _dump(target / "world.yaml", {"meta": payload["meta"], **payload["root"]})
    _dump(target / "taxonomy.yaml", payload["taxonomy"])
    if payload.get("scenario"):
        _dump(target / "scenario.yaml", payload["scenario"])

    children: dict[str | None, list[dict]] = {}
    for node in payload.get("nodes", []):
        children.setdefault(node.get("parent"), []).append(node)
    root_slug = target.name
    has_children = {n["slug"] for n in payload.get("nodes", [])} & set(
        c.get("parent") for c in payload.get("nodes", [])
    )

    def write_subtree(node: dict, directory: Path) -> None:
        slug = node["slug"]
        body = {k: v for k, v in node.items() if k not in ("slug", "parent")}
        if slug in has_children:
            _dump(directory / slug / "_node.yaml", body)
            for child in children.get(slug, []):
                write_subtree(child, directory / slug)
        else:
            _dump(directory / f"{slug}.yaml", body)

    for top in children.get(root_slug, []) + children.get(None, []):
        write_subtree(top, target / "nodes")

    for name in ("edges", "factions", "npcs", "encounters"):
        for entry in payload.get(name, []):
            body = {k: v for k, v in entry.items() if k != "slug"}
            _dump(target / name / f"{entry['slug']}.yaml", body)
