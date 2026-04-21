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
- Disposition toward player: {disposition}/100

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
{{"dialogue": "What you say", "action": "What you do (or null)", "disposition_change": 0, "reveals_secret": false}}

IMPORTANT: respond with valid JSON only. No markdown fences, no explanation."""


def build_npc_prompt(
    npc_data: dict,
    player_action: str = "",
    dm_narration: str = "",
) -> str:
    # Personality: handle both flat string (template) and dict (legacy)
    personality_raw = npc_data.get("personality", "")
    if isinstance(personality_raw, dict):
        traits = personality_raw.get("traits", [])
        fears = personality_raw.get("fears", [])
        dict_secrets = personality_raw.get("secrets", [])
        personality_str = ", ".join(traits) if traits else "unremarkable"
    else:
        fears = []
        dict_secrets = []
        personality_str = str(personality_raw) if personality_raw else "unremarkable"

    # Motivation: flat string (template) or list via "goals" (legacy)
    motivation_raw = npc_data.get("motivation", "")
    if not motivation_raw:
        goals = npc_data.get("goals", ["Survive"])
        motivation_str = ", ".join(goals) if isinstance(goals, list) else str(goals)
    else:
        motivation_str = str(motivation_raw)

    # Secret: dict.secrets (legacy) → flat secret (template) → fallback
    if dict_secrets:
        secret_str = ", ".join(dict_secrets)
    else:
        secret_raw = npc_data.get("secret", "")
        secret_str = str(secret_raw) if secret_raw else "None"

    # Fear: from personality.fears (legacy) or npc_data.fear (fallback)
    fear_str = ", ".join(fears) if fears else npc_data.get("fear", "")

    disposition = npc_data.get("disposition_toward_player", npc_data.get("disposition", 0))

    # Last interactions (ring buffer, max 3)
    last_interactions: list[str] = npc_data.get("last_interactions", [])
    if last_interactions:
        history_lines = "\n".join(f"  - {entry}" for entry in last_interactions[-3:])
        recent_history = f"\n## Recent history with player\n{history_lines}\n"
    else:
        recent_history = ""

    return NPC_BASE_PROMPT.format(
        name=npc_data.get("name", "Unknown"),
        role=npc_data.get("role", "Commoner"),
        location=npc_data.get("location", "Unknown"),
        personality=personality_str,
        motivation=motivation_str,
        fear=fear_str,
        secret=secret_str,
        disposition=disposition,
        player_action=player_action[:300],
        dm_narration=dm_narration[:500],
        recent_history=recent_history,
    )
