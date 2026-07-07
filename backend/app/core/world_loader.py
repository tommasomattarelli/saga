"""ADR 0008 — directory-convention World loader (D3/D3c/D5).

Walks a World directory, enforces filename-is-slug, builds the in-memory
asset. Covers validation tiers 1 (YAML parse) and 2 (Pydantic per-entity);
tier 3 (referential integrity) lives in `world_validator.py`.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from app.models.world import (
    EdgeDef,
    EncounterTable,
    FactionDef,
    NpcRecord,
    Position,
    ScenarioDef,
    Taxonomy,
    WorldMeta,
    WorldNode,
    WorldRootFile,
    is_valid_slug,
)


class WorldLoadError(Exception):
    pass


@dataclass
class WorldAsset:
    path: Path
    meta: WorldMeta
    taxonomy: Taxonomy
    root_slug: str
    nodes: dict[str, WorldNode] = field(default_factory=dict)
    parent: dict[str, str | None] = field(default_factory=dict)
    edges: dict[str, EdgeDef] = field(default_factory=dict)
    encounters: dict[str, EncounterTable] = field(default_factory=dict)
    factions: dict[str, FactionDef] = field(default_factory=dict)
    npcs: dict[str, NpcRecord] = field(default_factory=dict)
    scenario: ScenarioDef | None = None


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise WorldLoadError(f"{path.name}: invalid YAML — {exc}") from exc
    if not isinstance(data, dict):
        raise WorldLoadError(f"{path.name}: expected a YAML mapping")
    return data


def _parse[M: BaseModel](model: type[M], path: Path, data: dict, slug: str | None = None) -> M:
    if "slug" in data or "id" in data:
        raise WorldLoadError(
            f"{path.name}: 'slug'/'id' fields are forbidden — the filename is the slug (D3c)"
        )
    if slug is not None:
        data = {**data, "slug": slug}
    try:
        return model(**data)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise WorldLoadError(f"{path.name}: {first['msg']} ({first['loc']})") from exc


def _slug_of(path: Path) -> str:
    slug = path.parent.name if path.name == "_node.yaml" else path.stem
    if not is_valid_slug(slug):
        raise WorldLoadError(f"{path}: '{slug}' is not a valid kebab-case slug")
    return slug


def _add_node(asset: WorldAsset, node: WorldNode, parent_slug: str) -> None:
    if node.slug in asset.nodes:
        raise WorldLoadError(
            f"duplicate slug '{node.slug}' — slugs are globally unique in a World"
        )
    asset.nodes[node.slug] = node
    asset.parent[node.slug] = parent_slug


def _load_nodes(asset: WorldAsset, directory: Path, parent_slug: str) -> None:
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and entry.suffix == ".yaml" and entry.name != "_node.yaml":
            node = _parse(WorldNode, entry, _read_yaml(entry), slug=_slug_of(entry))
            _add_node(asset, node, parent_slug)
        elif entry.is_dir():
            node_file = entry / "_node.yaml"
            if not node_file.is_file():
                raise WorldLoadError(f"{entry}: node directory is missing _node.yaml")
            node = _parse(WorldNode, node_file, _read_yaml(node_file), slug=_slug_of(node_file))
            _add_node(asset, node, parent_slug)
            _load_nodes(asset, entry, node.slug)


def _load_collection[M: BaseModel](directory: Path, model: type[M], target: dict[str, M]) -> None:
    if not directory.is_dir():
        return
    for entry in sorted(directory.glob("*.yaml")):
        slug = _slug_of(entry)
        if slug in target:
            raise WorldLoadError(f"duplicate slug '{slug}' in {directory.name}/")
        target[slug] = _parse(model, entry, _read_yaml(entry), slug=slug)


def load_world(world_dir: Path) -> WorldAsset:
    world_dir = Path(world_dir)
    for required in ("world.yaml", "taxonomy.yaml"):
        if not (world_dir / required).is_file():
            raise WorldLoadError(f"{world_dir}: missing {required}")

    taxonomy_data = _read_yaml(world_dir / "taxonomy.yaml")
    try:
        taxonomy = Taxonomy(**taxonomy_data)
    except ValidationError as exc:
        raise WorldLoadError(f"taxonomy.yaml: {exc.errors()[0]['msg']}") from exc

    root_data = _read_yaml(world_dir / "world.yaml")
    root_file = _parse(WorldRootFile, world_dir / "world.yaml", root_data)
    root_slug = world_dir.name
    if not is_valid_slug(root_slug):
        raise WorldLoadError(f"world directory name '{root_slug}' is not a valid slug")

    asset = WorldAsset(path=world_dir, meta=root_file.meta, taxonomy=taxonomy, root_slug=root_slug)
    root_node = WorldNode(
        slug=root_slug,
        kind=root_file.kind,
        name=root_file.meta.name,
        description=root_file.description,
        position=Position(x=0, y=0),
        elevation_m=root_file.elevation_m,
        terrain=root_file.terrain,
        km_per_unit=root_file.km_per_unit,
        map_image=root_file.map_image,
        params=root_file.params,
        items=root_file.items,
    )
    asset.nodes[root_slug] = root_node
    asset.parent[root_slug] = None

    nodes_dir = world_dir / "nodes"
    if nodes_dir.is_dir():
        _load_nodes(asset, nodes_dir, root_slug)

    _load_collection(world_dir / "edges", EdgeDef, asset.edges)
    _load_collection(world_dir / "encounters", EncounterTable, asset.encounters)
    _load_collection(world_dir / "factions", FactionDef, asset.factions)
    _load_collection(world_dir / "npcs", NpcRecord, asset.npcs)

    scenario_file = world_dir / "scenario.yaml"
    if scenario_file.is_file():
        data = _read_yaml(scenario_file)
        asset.scenario = _parse(ScenarioDef, scenario_file, data)

    return asset
