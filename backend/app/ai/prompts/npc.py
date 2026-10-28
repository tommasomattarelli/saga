"""NPC prompt — the NPC playing itself sees its full traits (ADR 0009 G3)."""

from app.ai.prompts.loader import template
from app.core.campaign_language import LANGUAGES, validate_language
from app.core.psychology import DEFAULT_PSYCHOLOGY, band_label
from app.models.psychology import PsychologyDef

NPC_BASE_PROMPT = template("npc", "base")


def _render_axes(npc_data: dict, pdef: PsychologyDef) -> str:
    values = npc_data.get("psychology", {})
    lines = []
    for name, axis in pdef.axes.items():
        value = values.get(name, axis.default)
        lo, hi = axis.range
        lines.append(f"  - {name}: {value} ({band_label(axis, value)}) [range {lo}..{hi}]")
    return "\n".join(lines)


def _render_traits(traits: dict) -> tuple[str, list[str]]:
    """Returns (block of established facts, names of empty traits)."""
    lines: list[str] = []
    empty: list[str] = []
    for key, value in traits.items():
        if value:
            lines.append(f"- {key.replace('_', ' ').capitalize()}: {value}")
        else:
            empty.append(key)
    block = "\n".join(lines) or template("npc", "empty_traits")
    return block, empty


def build_npc_prompt(
    npc_data: dict,
    player_action: str = "",
    dm_narration: str = "",
    psychology: PsychologyDef | None = None,
    fill_empty_traits: bool = False,
    language: str = "en",
) -> str:
    pdef = psychology or DEFAULT_PSYCHOLOGY
    traits_block, empty = _render_traits(npc_data.get("traits", {}))

    # D2 rich level: the NPC invents its own missing facts, in character.
    fill_guidance = ""
    if fill_empty_traits and empty:
        fill_guidance = template("npc", "fill_guidance").format(names=", ".join(empty))

    last_interactions: list[str] = npc_data.get("last_interactions", [])
    if last_interactions:
        history_lines = "\n".join(f"  - {entry}" for entry in last_interactions[-3:])
        recent_history = template("npc", "recent_history").format(entries=history_lines)
    else:
        recent_history = ""

    return NPC_BASE_PROMPT.format(
        campaign_language=f"{LANGUAGES[validate_language(language)]} ({language})",
        name=npc_data.get("name", "Unknown"),
        location=npc_data.get("location_name") or "Unknown",
        traits_block=traits_block,
        fill_guidance=fill_guidance,
        axes_block=_render_axes(npc_data, pdef),
        axis_names=", ".join(pdef.axes),
        max_delta=pdef.max_delta_per_turn,
        player_action=player_action[:300],
        dm_narration=dm_narration[:500],
        recent_history=recent_history,
    )
