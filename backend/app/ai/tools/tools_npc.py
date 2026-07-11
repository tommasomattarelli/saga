"""ADR 0009 — NPC record mutation tools (update_npc; lifecycle tools in H2/H3).

`update_npc` writes only the B2-mutable engine fields plus the world's declared
npc_fields (traits). Lifecycle, psychology, met_player have their own owners
and are never writable here (A3/B1).
"""

from __future__ import annotations

import difflib
from uuid import uuid4

from pydantic import Field

from app.ai.tools.tools_base import DmTool, ToolResult, register
from app.core.npc_fields import resolve_npc_fields
from app.core.npc_resolver import resolve_npc
from app.core.npc_scaffold import create_npc_record
from app.core.psychology import resolve_psychology
from app.core.world_access import WorldView

# Wired to saga.config.yaml in the config commit (std 14).
DEFAULT_NAME_MATCH_THRESHOLD = 0.85

_ENGINE_WRITABLE = ("name", "condition", "location", "faction")


def _npc_aliases(world_state: dict) -> list[str]:
    aliases: list[str] = []
    for npc in world_state.get("npcs", {}).values():
        aliases.extend(a for a in (npc.get("name"), npc.get("slug")) if a)
    return aliases


@register
class UpdateNpc(DmTool):
    name: str = Field(description="NPC name — an existing NPC to update, or a new one to create")
    updates: dict[str, str] = Field(
        description="Field → new value. Writable: name (rename = identity reveal, never a "
        "re-cast), condition, location, faction, plus this world's NPC trait fields."
    )
    create: bool = Field(
        default=False,
        description="Set true ONLY to force-create a brand-new NPC whose name is close to "
        "an existing one.",
    )

    @classmethod
    def tool_name(cls) -> str:
        return "update_npc"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Create a new NPC or update an existing one's descriptive facts. "
            "Never changes psychology (use change_npc_psychology) or life state."
        )

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        return self.execute_with_baseline(world_state, char_data, None)

    def execute_with_baseline(
        self, world_state: dict, char_data: dict, baseline: dict | None
    ) -> ToolResult:
        def reject(message: str) -> ToolResult:
            return ToolResult(description=message, world_state=world_state, char_data=char_data)

        taxonomy = (baseline or {}).get("taxonomy")
        declared = [f.name for f in resolve_npc_fields(taxonomy)]

        for key in self.updates:
            if key not in _ENGINE_WRITABLE and key not in declared:
                return reject(
                    f"Field '{key}' is not writable. Writable: {', '.join(_ENGINE_WRITABLE)} "
                    f"+ traits: {', '.join(declared)}. Life state and psychology have "
                    "dedicated tools."
                )

        location_error, updates = self._resolve_location(dict(self.updates), world_state, baseline)
        if location_error:
            return reject(location_error)

        resolution = resolve_npc(self.name, world_state)
        if resolution.candidates:
            return reject(f"Multiple NPCs match '{self.name}' — specify which one.")

        if resolution.npc_id is not None:
            npc = world_state["npcs"][resolution.npc_id]
            verb = "updated"
        else:
            near = difflib.get_close_matches(
                self.name,
                _npc_aliases(world_state),
                n=3,
                cutoff=DEFAULT_NAME_MATCH_THRESHOLD,
            )
            if near and not self.create:
                return reject(
                    f"No NPC named '{self.name}'. Did you mean: {', '.join(near)}? "
                    f"To create a NEW npc named {self.name}, call again with create=true."
                )
            npc = create_npc_record(
                self.name,
                psychology=resolve_psychology(taxonomy),
                npc_fields=resolve_npc_fields(taxonomy),
            )
            world_state.setdefault("npcs", {})[str(uuid4())] = npc
            verb = "created"

        applied = []
        for key, value in updates.items():
            if key in _ENGINE_WRITABLE:
                npc[key] = value
            else:
                npc.setdefault("traits", {})[key] = value
            applied.append(f"{key}={value!r}")

        return ToolResult(
            description=f"{npc['name']} {verb}: {', '.join(applied) or 'no changes'}",
            world_state=world_state,
            char_data=char_data,
        )

    @staticmethod
    def _resolve_location(
        updates: dict[str, str], world_state: dict, baseline: dict | None
    ) -> tuple[str, dict[str, str]]:
        """Resolve a location value to a node uuid (E1 — 0008 scoped resolution)."""
        place = updates.get("location")
        if place is None or not baseline:
            return "", updates
        result = WorldView(baseline, world_state).resolve(place)
        if result.match is None:
            return f"Unknown place '{place}' — the NPC's location was not changed.", updates
        updates["location"] = result.match
        return "", updates
