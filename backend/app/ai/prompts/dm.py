"""DM system prompt — agentic version with XML structure and selective context."""

from pathlib import Path

import yaml

from app.ai.prompts.presets import PERSONA_PRESETS
from app.ai.prompts.scene import render_location_block
from app.core.npc_fields import resolve_npc_fields
from app.core.npc_resolver import npcs_at_current_location
from app.core.psychology import band_label, is_salient, resolve_psychology
from app.core.world_access import WorldView
from app.models.campaign import Campaign
from app.models.psychology import PsychologyDef

_PROMPTS = yaml.safe_load((Path(__file__).parent / "dm.yaml").read_text(encoding="utf-8"))

BASE_DM_PROMPT: str = _PROMPTS["base_dm_prompt"]
DEATH_MODE_PROMPTS: dict[str, str] = _PROMPTS["death_mode_prompts"]


def _salient_axis_attrs(npc: dict, psychology: PsychologyDef) -> str:
    """Axes outside their default band, as XML attributes (ADR 0005 A5)."""
    values = npc.get("psychology", {})
    attrs = []
    for name, axis in psychology.axes.items():
        value = values.get(name, axis.default)
        if is_salient(axis, value):
            attrs.append(f'{name}="{band_label(axis, value)}"')
    return (" " + " ".join(attrs)) if attrs else ""


def build_dm_system_prompt(
    campaign: Campaign,
    summary_context: str = "",
    global_summary: str = "",
    recalled_memories: list[str] | None = None,
) -> str:
    world_state = campaign.world_state or {}
    char_data = campaign.character_data or {}

    current_location = world_state.get("meta", {}).get("current_location", "")
    time_of_day = world_state.get("time_of_day", "")
    season = world_state.get("meta", {}).get("current_season", "")
    weather = world_state.get("weather", "")

    # Clock: compute day from total_minutes
    clock = world_state.get("clock", {})
    total_minutes = clock.get("total_minutes", 0)
    current_day = (total_minutes // (60 * 24)) + 1
    time_str = f"Day {current_day}, {time_of_day}, {season}".strip(", ")

    # Character vitals
    char_name = char_data.get("name", "Hero")
    hp = char_data.get("hp", "?")
    max_hp = char_data.get("max_hp", "?")

    ability_keys = [
        ("STR", "str"),
        ("DEX", "dex"),
        ("CON", "con"),
        ("INT", "int"),
        ("WIS", "wis"),
        ("CHA", "cha"),
    ]
    ability_parts = [
        f"{label} {char_data[key]}" for label, key in ability_keys if key in char_data
    ]

    inventory = char_data.get("inventory", [])
    inventory_str = ", ".join(str(i) for i in inventory) if inventory else "nothing notable"

    # Hierarchical world view (ADR 0008); legacy flat locations as fallback
    view = WorldView(getattr(campaign, "world_baseline", None) or {}, world_state)
    position = view.player_position() if view.has_world else None
    location_display = current_location
    if position and view.node(position):
        location_display = view.require(position)["name"]

    loc_data = world_state.get("locations", {}).get(current_location, {})
    loc_desc = loc_data.get("description", "")
    loc_connections = loc_data.get("connections", [])

    # NPCs present at current location
    npcs_present = npcs_at_current_location(world_state)

    # Death mode
    death_prompt = DEATH_MODE_PROMPTS.get(campaign.death_mode, "")

    lines: list[str] = []

    # <persona> — optional DM tone block, injected before <instructions>
    persona_xml = getattr(campaign, "persona_xml", None)
    persona_xml = persona_xml if isinstance(persona_xml, str) and persona_xml.strip() else None
    if not persona_xml:
        preset = getattr(campaign, "persona_preset", None)
        if isinstance(preset, str) and preset:
            persona_xml = PERSONA_PRESETS.get(preset)
    if persona_xml:
        lines.append(persona_xml.strip())

    # <instructions> — leading newline keeps the blank line before the death block
    lines.append(f"<instructions>\n{BASE_DM_PROMPT}")
    if death_prompt:
        lines.append(f"\n{death_prompt}")
    lines.append("</instructions>")

    # <character>
    loc_attr = f' location="{location_display}"' if location_display else ""
    lines.append(f'\n<character name="{char_name}" hp="{hp}/{max_hp}"{loc_attr}>')
    if ability_parts:
        lines.append(f"  <abilities>{', '.join(ability_parts)}</abilities>")
    lines.append(f"  <inventory>{inventory_str}</inventory>")
    lines.append("</character>")

    # <scene>
    lines.append("\n<scene>")
    if position and view.node(position):
        lines.extend(render_location_block(view, position))
    else:
        lines.append(f'  <location name="{current_location}">')
        if loc_desc:
            lines.append(f"    {loc_desc}")
        if loc_connections:
            lines.append(f"    Connected to: {', '.join(loc_connections)}.")
        lines.append("  </location>")

    if npcs_present:
        baseline = getattr(campaign, "world_baseline", None)
        taxonomy = baseline.get("taxonomy") if isinstance(baseline, dict) else None
        psychology = resolve_psychology(taxonomy)
        # G3: only scene-flagged traits reach the DM; the rest is npc_director-only.
        scene_fields = [f.name for f in resolve_npc_fields(taxonomy) if f.scene]
        lines.append("  <npcs_present>")
        for npc in npcs_present.values():
            traits = npc.get("traits", {})
            attrs = "".join(
                f' {name}="{traits[name]}"' for name in scene_fields if traits.get(name)
            )
            if npc.get("condition"):
                attrs += f' condition="{npc["condition"]}"'
            axes = _salient_axis_attrs(npc, psychology)
            lines.append(f'    <npc name="{npc.get("name", "")}"{attrs}{axes}/>')
        lines.append("  </npcs_present>")

    if time_str:
        lines.append(f"  <time>{time_str}</time>")
    if weather:
        lines.append(f"  <weather>{weather}</weather>")

    lines.append("</scene>")

    # <global_summary> — rolling story arc (campaign-spanning)
    if global_summary and global_summary.strip():
        lines.append(f"\n<global_summary>\n{global_summary.strip()}\n</global_summary>")

    # <history> — batch summaries of recent turns outside the Active Window
    if summary_context:
        lines.append(f'\n<history label="story_so_far">\n{summary_context}\n</history>')

    # <recalled_memories> — targeted pgvector retrieval for current action
    if recalled_memories:
        lines.append("\n<recalled_memories>")
        for memory in recalled_memories:
            if memory and memory.strip():
                lines.append(f"  - {memory.strip()}")
        lines.append("</recalled_memories>")

    # <quests>
    active_quests = campaign.quests.get("active", []) if campaign.quests else []
    if active_quests:
        lines.append("\n<quests>")
        for q in active_quests:
            if isinstance(q, dict):
                lines.append(f'  <quest name="{q.get("name", "Unknown")}" status="active"/>')
            else:
                lines.append(f'  <quest name="{q}" status="active"/>')
        lines.append("</quests>")

    return "\n".join(lines)
