"""NPC prompt — the NPC playing itself sees its full traits (ADR 0009 G3)."""

from app.core.psychology import DEFAULT_PSYCHOLOGY, band_label
from app.models.psychology import PsychologyDef

NPC_BASE_PROMPT = """You are an NPC in a tabletop RPG. You have your own life, goals, and psychology.

## Your Identity
- Name: {name}
- Location: {location}

## Your Character
{traits_block}
{fill_guidance}
## How you feel about the player
{axes_block}

## What just happened
The player did: "{player_action}"
The DM narrated: "{dm_narration}"
{recent_history}
## Rules
- You do NOT exist to serve the player. You have your own agenda.
- React realistically to the player's approach (intimidation, charm, deception)
- You may lie, refuse, or be unhelpful if it fits your character
- If threatened, respond as a real person would (comply, flee, fight, call for help)
- Keep dialogue natural and period-appropriate
- Respond in 1-3 sentences, in character

Respond as JSON:
{{"dialogue": "What you say", "action": "What you do (or null)", "axis_changes": {{}}, "reveals_secret": false}}

In axis_changes report how this exchange shifted your feelings — only these axes: {axis_names}.
Integer deltas, max ±{max_delta} each; omit axes that did not move.

IMPORTANT: respond with valid JSON only. No markdown fences, no explanation."""


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
    block = "\n".join(lines) or "- (no established facts about you yet)"
    return block, empty


def build_npc_prompt(
    npc_data: dict,
    player_action: str = "",
    dm_narration: str = "",
    psychology: PsychologyDef | None = None,
    fill_empty_traits: bool = False,
) -> str:
    pdef = psychology or DEFAULT_PSYCHOLOGY
    traits_block, empty = _render_traits(npc_data.get("traits", {}))

    # D2 rich level: the NPC invents its own missing facts, in character.
    fill_guidance = ""
    if fill_empty_traits and empty:
        fill_guidance = (
            f"\nNot yet established about you: {', '.join(empty)}. "
            "Invent them in character as they come up, and stay consistent.\n"
        )

    last_interactions: list[str] = npc_data.get("last_interactions", [])
    if last_interactions:
        history_lines = "\n".join(f"  - {entry}" for entry in last_interactions[-3:])
        recent_history = f"\n## Recent history with player\n{history_lines}\n"
    else:
        recent_history = ""

    return NPC_BASE_PROMPT.format(
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
