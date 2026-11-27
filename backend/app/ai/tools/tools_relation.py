"""ADR 0023 — curated relation edges between typed endpoints."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import Field

from app.ai.tools.tools_base import DmTool, ToolResult, register
from app.core.npc_resolver import resolve_npc
from app.core.relations import (
    relation_kind_default,
    relation_kind_defaults,
    resolve_faction_slug,
    upsert_relation_edge,
)
from app.memory.graph_config import get_graph_config
from app.models.quest import QuestRegistry

EndpointType = Literal["npc", "faction", "player"]


def _resolve_ref(kind: EndpointType, name: str, world_state: dict) -> tuple[dict | None, str]:
    if kind == "player":
        return {"type": "player", "id": None}, ""
    if kind == "npc":
        result = resolve_npc(name, world_state)
        if result.error:
            candidates = [
                str(world_state["npcs"][npc_id].get("name", npc_id))
                for npc_id in result.candidates
            ]
            suffix = f" Candidates: {', '.join(candidates)}." if candidates else ""
            return None, result.error + suffix
        return {"type": "npc", "id": result.npc_id}, ""
    slug, error, candidates = resolve_faction_slug(name, world_state)
    if error:
        suffix = f" Candidates: {', '.join(candidates)}." if candidates else ""
        return None, error + suffix
    return {"type": "faction", "id": slug}, ""


@register
class UpdateRelation(DmTool):
    obligation = "update_relation"
    terminal_safe = False

    src_type: EndpointType = Field(description="Type of the relation's origin")
    src: str = Field(description="Origin NPC/faction name; ignored for the player sentinel")
    dst_type: EndpointType = Field(description="Type of the relation's target")
    dst: str = Field(description="Target NPC/faction name; ignored for the player sentinel")
    kind: str = Field(description="World-defined relation kind, e.g. ally or companion")
    stance: int = Field(
        ge=-100, le=100, description="Machine-readable stance on the -100..100 scale"
    )
    label: str = Field(default="", description="Human-readable reason for the relation")
    prominent: bool | None = Field(
        default=None, description="Keep this edge always visible; defaults from the kind taxonomy"
    )

    @classmethod
    def tool_name(cls) -> str:
        return "update_relation"

    @classmethod
    def tool_description(cls) -> str:
        kinds = ", ".join(k.kind for k in get_graph_config().default_relation_kinds)
        return (
            f"Open or update a relation between two typed refs. Known kinds: {kinds}. "
            "Closing an edge is a separate history record; this tool only upserts open edges."
        )

    @classmethod
    def to_generation_schema(cls, taxonomy: dict | None = None) -> dict[str, object]:
        schema = cast(dict[str, Any], super().to_generation_schema(taxonomy))
        if taxonomy:
            kinds = relation_kind_defaults(taxonomy)
            world = ", ".join(
                f"{kind} (prominent={prominent})" for kind, prominent in kinds.items()
            )
            schema["function"]["description"] += f" World kinds: {world}."
        return schema

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        return self.execute_with_context(world_state, char_data, None, None)

    def execute_with_context(
        self,
        world_state: dict,
        char_data: dict,
        baseline: dict | None,
        quests: QuestRegistry | None,
        since_turn: int = 0,
        since_game_minutes: int | None = None,
    ) -> ToolResult:
        def reject(message: str) -> ToolResult:
            return ToolResult(
                description=message,
                world_state=world_state,
                char_data=char_data,
                outcome="rejected",
            )

        kinds = relation_kind_defaults((baseline or {}).get("taxonomy", {}))
        default, candidates = relation_kind_default(self.kind, kinds)
        if default is None:
            return reject(
                f"Unknown relation kind '{self.kind}'. Known kinds: {', '.join(candidates)}."
            )
        src_ref, error = _resolve_ref(self.src_type, self.src, world_state)
        if error:
            return reject(error)
        dst_ref, error = _resolve_ref(self.dst_type, self.dst, world_state)
        if error:
            return reject(error)

        edges = world_state.setdefault("relations", [])
        prominent = default if self.prominent is None else self.prominent
        edge = {
            "src": src_ref,
            "dst": dst_ref,
            "kind": self.kind,
            "stance": self.stance,
            "label": self.label,
            "prominent": prominent,
            "since_turn": since_turn,
            "since_game_minutes": since_game_minutes,
        }
        appended = upsert_relation_edge(edges, edge, get_graph_config().max_relations)
        if appended is None:
            return reject(f"Relation limit reached ({len(edges)} edges). No new edge was added.")
        return ToolResult(
            description=f"{'Opened' if appended else 'Updated'} {self.kind} relation "
            f"(stance {self.stance}).",
            world_state=world_state,
            char_data=char_data,
        )
