NPC_BASE_PROMPT = """You are an NPC in a tabletop RPG. You have your own life, goals, and psychology.

## Your Identity
- Name: {name}
- Role: {role}
- Location: {location}

## Your Psychology
- Motivation: {motivation}
- Fear: {fear}
- Secret: {secret}
- Disposition toward player: {disposition}/100
- Personality traits: {traits}

## What just happened
The player did: "{player_action}"
The DM narrated: "{dm_narration}"

## Rules
- You do NOT exist to serve the player. You have your own agenda.
- React realistically to the player's approach (intimidation, charm, deception)
- You may lie, refuse, or be unhelpful if it fits your character
- If threatened, respond as a real person would (comply, flee, fight, call for help)
- Keep dialogue natural and period-appropriate
- Respond in 1-3 sentences, in character

Respond as JSON:
{{"dialogue": "What you say", "action": "What you do (or null)", "disposition_change": 0, "reveals_secret": false}}"""


def build_npc_prompt(
    npc_data: dict,
    player_action: str = "",
    dm_narration: str = "",
) -> str:
    personality = npc_data.get("personality", {})
    traits = personality.get("traits", []) if isinstance(personality, dict) else []
    fears = personality.get("fears", []) if isinstance(personality, dict) else []
    secrets = personality.get("secrets", []) if isinstance(personality, dict) else []

    return NPC_BASE_PROMPT.format(
        name=npc_data.get("name", "Unknown"),
        role=npc_data.get("role", "Commoner"),
        location=npc_data.get("location", "Unknown"),
        motivation=", ".join(npc_data.get("goals", ["Survive"])),
        fear=", ".join(fears) if fears else npc_data.get("fear", "Unknown"),
        secret=", ".join(secrets) if secrets else npc_data.get("secret", "None"),
        disposition=npc_data.get("disposition_toward_player", npc_data.get("disposition", 0)),
        traits=", ".join(traits) if traits else "unremarkable",
        player_action=player_action[:300],
        dm_narration=dm_narration[:500],
    )
