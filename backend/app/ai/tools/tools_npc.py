"""ADR 0009 — NPC record mutation tools (update_npc; lifecycle tools in H2/H3).

`update_npc` writes only the B2-mutable engine fields plus the world's declared
npc_fields (traits). Lifecycle, psychology, met_player have their own owners
and are never writable here (A3/B1).
"""

from __future__ import annotations

import difflib
from uuid import uuid4

from pydantic import Field

from app.ai.router import get_gameplay_config
from app.ai.tools.tools_base import DmTool, ToolResult, register
from app.core.npc_fields import resolve_npc_fields
from app.core.npc_resolver import resolve_npc
from app.core.npc_scaffold import create_npc_record
from app.core.psychology import resolve_psychology
from app.core.world_access import WorldView

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
        gameplay = get_gameplay_config()

        for key in self.updates:
            if key not in _ENGINE_WRITABLE and key not in declared:
                return reject(
                    f"Field '{key}' is not writable. Writable: {', '.join(_ENGINE_WRITABLE)} "
                    f"+ traits: {', '.join(declared)}. Life state and psychology have "
                    "dedicated tools."
                )

        condition = self.updates.get("condition")
        if condition and len(condition) > gameplay.npc_condition_max_chars:
            return reject(
                f"condition too long ({len(condition)} chars, "
                f"max {gameplay.npc_condition_max_chars}) — shorten it."
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
                cutoff=gameplay.npc_name_match_threshold,
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


# ── Lifecycle tools (H2/H3) — the only DM-facing lifecycle writers ───────────


def _reject(world_state: dict, char_data: dict, message: str) -> ToolResult:
    return ToolResult(description=message, world_state=world_state, char_data=char_data)


@register
class KillNpc(DmTool):
    name: str = Field(description="Exact name of the NPC that dies")
    cause: str = Field(description="Brief cause of death (e.g. 'duel', 'poison')")

    @classmethod
    def tool_name(cls) -> str:
        return "kill_npc"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Kill an NPC on-screen, outside combat (execution, poison, story). "
            "Irreversible. The NPC must be present in the current scene. "
            "In combat, death happens automatically at 0 HP — don't call this."
        )

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        resolution = resolve_npc(self.name, world_state)
        if resolution.npc_id is None:
            return _reject(world_state, char_data, resolution.error)
        npc = world_state["npcs"][resolution.npc_id]
        current = world_state.get("meta", {}).get("current_location")
        if current and npc.get("location") and npc["location"] != current:
            return _reject(
                world_state, char_data, f"{npc['name']} is elsewhere and cannot be killed here."
            )
        npc["lifecycle"] = "dead"
        return ToolResult(
            description=f"{npc['name']} is dead ({self.cause}). Narrate the death.",
            world_state=world_state,
            char_data=char_data,
        )


@register
class RemoveNpc(DmTool):
    name: str = Field(description="Exact name of the NPC leaving the story")
    reason: str = Field(description="Why they leave (e.g. 'departed for the capital')")

    @classmethod
    def tool_name(cls) -> str:
        return "remove_npc"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Move a living NPC off-stage (departed, exiled, vanished). The record is "
            "kept and the NPC can return later via restore_npc. Not a death."
        )

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        resolution = resolve_npc(self.name, world_state)
        if resolution.npc_id is None:
            return _reject(world_state, char_data, resolution.error)
        npc = world_state["npcs"][resolution.npc_id]
        npc["lifecycle"] = "removed"
        return ToolResult(
            description=f"{npc['name']} leaves the story ({self.reason}).",
            world_state=world_state,
            char_data=char_data,
        )


@register
class RestoreNpc(DmTool):
    name: str = Field(description="Exact name of the removed NPC returning to the story")
    location: str | None = Field(default=None, description="Where they reappear (place name)")

    @classmethod
    def tool_name(cls) -> str:
        return "restore_npc"

    @classmethod
    def tool_description(cls) -> str:
        return "Bring a previously removed NPC back on-stage. Dead NPCs cannot return."

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        return self.execute_with_baseline(world_state, char_data, None)

    def execute_with_baseline(
        self, world_state: dict, char_data: dict, baseline: dict | None
    ) -> ToolResult:
        resolution = resolve_npc(self.name, world_state, include_gone=True)
        if resolution.npc_id is None:
            if resolution.candidates:
                return _reject(
                    world_state, char_data, f"Multiple NPCs match '{self.name}' — specify."
                )
            return _reject(world_state, char_data, resolution.error)
        npc = world_state["npcs"][resolution.npc_id]
        if npc.get("lifecycle") == "dead":
            return _reject(world_state, char_data, f"{npc['name']} is dead — death is final.")
        if npc.get("lifecycle") != "removed":
            return _reject(world_state, char_data, f"{npc['name']} is already present.")
        if self.location and baseline:
            result = WorldView(baseline, world_state).resolve(self.location)
            if result.match is None:
                return _reject(world_state, char_data, f"Unknown place '{self.location}'.")
            npc["location"] = result.match
        npc["lifecycle"] = "alive"
        return ToolResult(
            description=f"{npc['name']} returns to the story.",
            world_state=world_state,
            char_data=char_data,
        )
