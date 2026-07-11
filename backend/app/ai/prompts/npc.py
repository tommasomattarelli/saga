from app.core.psychology import DEFAULT_PSYCHOLOGY, band_label
from app.models.psychology import PsychologyDef

NPC_BASE_PROMPT = """You are an NPC in a tabletop RPG. You have your own life, goals, and psychology.

## Your Identity
- Name: {name}
- Role: {role}
- Location: {location}

## Your Psychology
- Personality: {personality}
- Motivation: {motivation}
- Fear: {fear}
- Secret: {secret}
- How you feel about the player:
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


def _trait(npc_data: dict, key: str, legacy_key: str | None = None) -> str | dict:
    # ADR 0009 G1: descriptives live in traits; flat reads kept as legacy fallback.
    traits = npc_data.get("traits", {})
    return traits.get(key) or npc_data.get(legacy_key or key, "")


def build_npc_prompt(
    npc_data: dict,
    player_action: str = "",
    dm_narration: str = "",
    psychology: PsychologyDef | None = None,
) -> str:
    # Personality: handle both flat string (template) and dict (legacy)
    fears: list[str] = []
    dict_secrets: list[str] = []
    personality_raw = _trait(npc_data, "personality")
    if isinstance(personality_raw, dict):
        traits = personality_raw.get("traits", [])
        fears = personality_raw.get("fears", [])
        dict_secrets = personality_raw.get("secrets", [])
        personality_str = ", ".join(traits) if traits else "unremarkable"
    else:
        personality_str = str(personality_raw) if personality_raw else "unremarkable"

    # Motivation: flat string (template) or list via "goals" (legacy)
    motivation_raw = _trait(npc_data, "motivation")
    if not motivation_raw:
        goals = npc_data.get("goals", ["Survive"])
        motivation_str = ", ".join(goals) if isinstance(goals, list) else str(goals)
    else:
        motivation_str = str(motivation_raw)

    # Secret: dict.secrets (legacy) → flat secret (template) → fallback
    if dict_secrets:
        secret_str = ", ".join(dict_secrets)
    else:
        secret_raw = _trait(npc_data, "secret")
        secret_str = str(secret_raw) if secret_raw else "None"

    # Dreads (renamed from fear, ADR 0009 G2): legacy personality.fears / fear fallback
    fear_str = ", ".join(fears) if fears else _trait(npc_data, "dreads", "fear")

    pdef = psychology or DEFAULT_PSYCHOLOGY

    # Last interactions (ring buffer, max 3)
    last_interactions: list[str] = npc_data.get("last_interactions", [])
    if last_interactions:
        history_lines = "\n".join(f"  - {entry}" for entry in last_interactions[-3:])
        recent_history = f"\n## Recent history with player\n{history_lines}\n"
    else:
        recent_history = ""

    return NPC_BASE_PROMPT.format(
        name=npc_data.get("name", "Unknown"),
        role=_trait(npc_data, "role") or "Commoner",
        location=npc_data.get("location", "Unknown"),
        personality=personality_str,
        motivation=motivation_str,
        fear=fear_str,
        secret=secret_str,
        axes_block=_render_axes(npc_data, pdef),
        axis_names=", ".join(pdef.axes),
        max_delta=pdef.max_delta_per_turn,
        player_action=player_action[:300],
        dm_narration=dm_narration[:500],
        recent_history=recent_history,
    )
