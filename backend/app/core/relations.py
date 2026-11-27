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
