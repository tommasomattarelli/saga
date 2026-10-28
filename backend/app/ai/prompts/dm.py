"""DM system prompt — agentic version with XML structure and selective context."""

from dataclasses import dataclass
from xml.sax.saxutils import escape

from app.ai.prompts.loader import template
from app.ai.prompts.obligations import compose_obligations
from app.ai.prompts.presets import PERSONA_PRESETS
from app.ai.prompts.scene import render_location_block
from app.ai.tools.tool_groups import resolve_active_tools_from_state
from app.core.campaign_language import LANGUAGES, validate_language
from app.core.health import hp_band
from app.core.npc_fields import resolve_npc_fields
from app.core.npc_resolver import npcs_at_current_location
from app.core.psychology import band_label, is_salient, resolve_psychology
from app.core.world_access import WorldView
from app.models.campaign import Campaign
from app.models.psychology import PsychologyDef
from app.models.quest import QuestRegistry

BASE_DM_PROMPT: str = template("dm", "base_dm_prompt")


@dataclass(frozen=True)
class DMPromptContext:
    language: str = "en"
    persona: str = ""
    summary_context: str = ""
    global_summary: str = ""
    recalled_memories: tuple[str, ...] = ()


@dataclass(frozen=True)
class DMPromptState:
    world_state: dict
    character_data: dict
    world_baseline: dict
    quests: QuestRegistry


def campaign_prompt_context(
    campaign: Campaign,
    summary_context: str = "",
    global_summary: str = "",
    recalled_memories: list[str] | None = None,
) -> DMPromptContext:
    persona = getattr(campaign, "persona_xml", None)
    if not isinstance(persona, str) or not persona.strip():
        preset = getattr(campaign, "persona_preset", None)
        persona = PERSONA_PRESETS.get(preset, "") if isinstance(preset, str) else ""
    language = getattr(campaign, "language", None)
    return DMPromptContext(
        language=validate_language(language) if isinstance(language, str) else "en",
        persona=persona.strip(),
        summary_context=summary_context,
        global_summary=global_summary,
        recalled_memories=tuple(recalled_memories or []),
    )


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
    *,
    allowed_tools: set[str] | None = None,
    closing: bool = False,
) -> str:
    scene = DMPromptState(
        world_state=campaign.world_state or {},
        character_data=campaign.character_data or {},
        world_baseline=getattr(campaign, "world_baseline", None) or {},
        quests=QuestRegistry.model_validate(campaign.quests or {}),
    )
    context = campaign_prompt_context(campaign, summary_context, global_summary, recalled_memories)
    active = (
        resolve_active_tools_from_state(scene.world_state)
        if allowed_tools is None
        else allowed_tools
    )
    return render_dm_prompt(scene, context, active, closing=closing)


def render_dm_prompt(
    scene: DMPromptState,
    context: DMPromptContext,
    allowed_tools: set[str],
    *,
    closing: bool = False,
) -> str:
    world_state = scene.world_state
    char_data = scene.character_data

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
    hp = hp_band(char_data.get("hp") or {})

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

    # Hierarchical world view (ADR 0008); campaigns without a world asset fall back to the name
    view = WorldView(scene.world_baseline, world_state)
    position = view.player_position() if view.has_world else None
    location_display = current_location
    if position and view.node(position):
        location_display = view.require(position)["name"]

    # NPCs present at current location
    npcs_present = npcs_at_current_location(world_state)

    lines: list[str] = []

    # <persona> — optional DM tone block, injected before <instructions>
    if context.persona:
        lines.append(f"<flavor>\n{context.persona}\n</flavor>")

    # ADR 0003 B8 — no static death block: those instructions reach the DM only when
    # the player actually hits 0, as the per-turn check's narrative_instruction.
    code = context.language
    instructions = BASE_DM_PROMPT.replace("{campaign_language}", f"{LANGUAGES[code]} ({code})")
    lines.append(f"<instructions>\n<dm_core>\n{instructions}\n</dm_core>")
    lines.append(f"<engine>\n{compose_obligations(allowed_tools)}\n</engine>")
    if closing:
        lines.append(template("dm", "closing"))
    lines.append("</instructions>")

    # <character>
    loc_attr = f' location="{location_display}"' if location_display else ""
    hp_attr = f' hp="{hp}"' if hp else ""
    lines.append(f'\n<character name="{char_name}"{hp_attr}{loc_attr}>')
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
        lines.append("  </location>")

    if npcs_present:
        baseline = scene.world_baseline
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
    if context.global_summary and context.global_summary.strip():
        lines.append(f"\n<global_summary>\n{context.global_summary.strip()}\n</global_summary>")

    # <history> — batch summaries of recent turns outside the Active Window
    if context.summary_context:
        lines.append(f'\n<history label="story_so_far">\n{context.summary_context}\n</history>')

    # <recalled_memories> — targeted pgvector retrieval for current action
    if context.recalled_memories:
        lines.append("\n<recalled_memories>")
        for memory in context.recalled_memories:
            if memory and memory.strip():
                lines.append(f"  - {memory.strip()}")
        lines.append("</recalled_memories>")

    # <quests> — ADR 0019 A5: active tags and descriptions only. No display names,
    # objectives or concluded archive in the permanent DM context.
    registry = scene.quests
    if registry.active:
        lines.append("\n<quests>")
        for quest in registry.active:
            lines.append(f'  <quest id="{quest.id}">{escape(quest.description)}</quest>')
        lines.append("</quests>")

    return "\n".join(lines)
