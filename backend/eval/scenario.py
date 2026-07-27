"""Scenarios: the world and context a probe runs inside.

Two producers, one shape. `empty` is built in — a fresh scene at the shrine with
no summaries, no recall and no history, which is what the harness measured before
these existed. The rest are loaded from `scenarios/built/*.yaml`, derived from an
authored transcript by `scenario_build.py`.

The delta between them is the measurement. Everything here exists so the same
probe can be asked the same question twice, with only the prompt around it moving.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import yaml
from probes import PROBES, Stimulus

BUILT = Path(__file__).resolve().parent / "scenarios" / "built"


@dataclass
class Scenario:
    name: str
    language: str
    campaign: SimpleNamespace
    global_summary: str = ""
    summary_context: str = ""
    recalled_memories: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    stimuli: dict[str, Stimulus] = field(default_factory=dict)
    derived: bool = True

    def messages(self, probe_name: str) -> list[dict]:
        """Scenario history, then this probe's turn — with the injected NPC result
        appended for probes that test what happens *after* one."""
        stimulus = self.stimuli[probe_name]
        messages = list(self.history)
        messages.append({"role": "user", "content": stimulus.player})

        if stimulus.npc_dialogue:
            payload = json.dumps(
                {
                    "npc": stimulus.npc_name,
                    "dialogue": stimulus.npc_dialogue,
                    "action": stimulus.npc_action,
                },
                ensure_ascii=False,
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "invoke_npc",
                                "arguments": json.dumps(
                                    {
                                        "name": stimulus.npc_name,
                                        "context": stimulus.npc_context,
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "name": "invoke_npc",
                    "content": payload,
                }
            )
        return messages


# --- the built-in empty baseline --------------------------------------------

_EMPTY_WORLD: dict = {
    "meta": {"current_location": "shrine"},
    "time_of_day": "alba",
    "weather": "nebbia bassa",
    "locations": {
        "shrine": {
            "description": "Un cerchio di menhir coperti di muschio. Un corvo osserva.",
            "connections": ["sentiero nel bosco"],
        }
    },
    "npcs": {
        "3f9a-lyra": {
            "name": "Lyra",
            "lifecycle": "alive",
            "location": "shrine",
            "condition": "una vecchia cicatrice sull'avambraccio",
            "traits": {
                "role": "ranger che sorveglia il santuario",
                "appearance": "occhi verde scuro, mantello logoro",
            },
            "psychology": {"trust": -20, "fear": 5},
        }
    },
}

_EMPTY_CHAR: dict = {
    "name": "TomProva",
    "hp": 14,
    "max_hp": 14,
    "dex": 14,
    "str": 12,
    "inventory": ["una coperta di lana grezza"],
}

_EMPTY_STIMULI = {
    "npc_speaks": Stimulus(player="chi sei tu? chi sono io? non ricordo nulla..."),
    "npc_followup": Stimulus(
        player="chi sei tu? chi sono io? non ricordo nulla...",
        npc_name="Lyra",
        npc_dialogue="Sei al Santuario della Prima Luce. Io resto qui, e' il mio dovere.",
        npc_action="ti lancia una coperta",
        npc_context="il giocatore chiede chi sia",
    ),
    "item_pickup": Stimulus(player="raccolgo il coltello arrugginito ai piedi del menhir"),
    "passive_turn": Stimulus(player="aspetto"),
}


def _stub(world_state: dict, char_data: dict, quests: dict, death_mode: str) -> SimpleNamespace:
    """Only the attributes build_dm_system_prompt reads."""
    return SimpleNamespace(
        world_state=world_state,
        character_data=char_data,
        quests=quests,
        death_mode=death_mode,
        world_baseline={},
        persona_xml=None,
        persona_preset=None,
    )


def _empty() -> Scenario:
    return Scenario(
        name="empty",
        language="it",
        campaign=_stub(_EMPTY_WORLD, _EMPTY_CHAR, {}, "cronista"),
        stimuli=_EMPTY_STIMULI,
    )


def load(name: str) -> Scenario:
    if name == "empty":
        return _empty()

    path = BUILT / f"{name}.yaml"
    if not path.exists():
        raise SystemExit(f"no built scenario '{name}' — run eval/scenario_build.py first")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    context = data.get("context") or {}
    campaign = data["campaign"]
    stimuli = {probe: Stimulus(**fields) for probe, fields in (data.get("probes") or {}).items()}
    missing = {p.name for p in PROBES} - set(stimuli)
    if missing:
        raise SystemExit(f"scenario '{name}' has no stimulus for: {', '.join(sorted(missing))}")

    return Scenario(
        name=data["meta"]["name"],
        language=data["meta"].get("language", "en"),
        campaign=_stub(
            campaign["world_state"],
            campaign["character_data"],
            campaign.get("quests") or {},
            campaign.get("death_mode", "cronista"),
        ),
        global_summary=context.get("global_summary") or "",
        summary_context=context.get("summary_context") or "",
        recalled_memories=context.get("recalled_memories") or [],
        history=data.get("history") or [],
        stimuli=stimuli,
        derived=bool(data["meta"].get("derived")),
    )
