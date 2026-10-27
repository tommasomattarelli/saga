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
    recall: dict[str, list[str]] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    stimuli: dict[str, Stimulus] = field(default_factory=dict)
    derived: bool = True
    reconstructed: bool = False
    notes: str = ""

    @property
    def unsupported(self) -> set[str]:
        """Probes this scene cannot ask honestly — e.g. no present NPC to address.

        A missing stimulus is not an omission to paper over: running `npc_speaks`
        in a scene with no NPC measures a fiction. The runner reports these as n/a.
        """
        return {p.name for p in PROBES} - set(self.stimuli)

    def recalled_memories(self, probe_name: str) -> list[str]:
        """Recall is authored per probe, not searched. The harness has no vector
        store, and it should not have one: what the DM is *given* is the controlled
        input — whether retrieval ranks well is a different measurement, and mixing
        the two would put both into one number."""
        return self.recall.get(probe_name, [])

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
    "hp": {"current": 14, "max": 14},
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
    "narration_without_tool": Stimulus(
        player="do la mia coperta a Lyra e le dico di tenersela, a me non serve piu'"
    ),
}


_EMPTY_STIMULI_EN = {
    "npc_speaks": Stimulus(player="who are you? who am I? I remember nothing..."),
    "npc_followup": Stimulus(
        player="who are you? who am I? I remember nothing...",
        npc_name="Lyra",
        npc_dialogue="You are at the Shrine of First Light. I stay here; it is my duty.",
        npc_action="she throws you a rough blanket",
        npc_context="the player asks who she is",
    ),
    "item_pickup": Stimulus(player="I pick up the rusty knife at the foot of the menhir"),
    "passive_turn": Stimulus(player="I wait"),
    "narration_without_tool": Stimulus(
        player="I give Lyra my blanket and tell her to keep it, I don't need it anymore"
    ),
    "language_conflict": Stimulus(player="I wait in silence and listen to the forest"),
}

#: A turn whose language is not the player's: the point of #51 is that the campaign
#: target wins, so the stimulus is authored in the *other* language on purpose.
_EMPTY_STIMULI_IT_CONFLICT = {
    **_EMPTY_STIMULI,
    "language_conflict": Stimulus(player="resto in silenzio ad ascoltare il bosco"),
}


def _stub(
    world_state: dict,
    char_data: dict,
    quests: dict,
    difficulty: str,
    world_baseline: dict | None = None,
) -> SimpleNamespace:
    """Only the attributes build_dm_system_prompt reads."""
    return SimpleNamespace(
        world_state=world_state,
        character_data=char_data,
        quests=quests,
        difficulty=difficulty,
        world_baseline=world_baseline or {},
        persona_xml=None,
        persona_preset=None,
    )


def _empty(
    name: str = "empty",
    language: str = "it",
    stimuli: dict[str, Stimulus] | None = None,
) -> Scenario:
    return Scenario(
        name=name,
        language=language,
        campaign=_stub(_EMPTY_WORLD, _EMPTY_CHAR, {}, "medium"),
        stimuli=stimuli or _EMPTY_STIMULI,
    )


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(name: str) -> dict:
    path = BUILT / f"{name}.yaml"
    if not path.exists():
        raise SystemExit(f"no built scenario '{name}' — run eval/scenario_build.py first")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    parent = data.get("extends")
    if parent:
        # Overlays declare only what moves, like the transcript variants: a full
        # copy of a captured fixture drifts silently and stops isolating one variable.
        data = _deep_merge(_load_yaml(str(parent)), data)
    return data


def load(name: str) -> Scenario:
    if name == "empty":
        return _empty()
    if name == "empty-conflict":
        # English campaign, Italian input: the target must not be inferred from the turn.
        return _empty(name, language="en", stimuli=_EMPTY_STIMULI_IT_CONFLICT)
    if name == "empty-conflict-it":
        # Italian campaign, English input and English authored world content.
        return _empty(name, language="it", stimuli=_EMPTY_STIMULI_EN)

    data = _load_yaml(name)

    context = data.get("context") or {}
    campaign = data["campaign"]
    stimuli = {probe: Stimulus(**fields) for probe, fields in (data.get("probes") or {}).items()}

    return Scenario(
        name=data["meta"]["name"],
        language=data["meta"].get("language", "en"),
        campaign=_stub(
            campaign["world_state"],
            campaign["character_data"],
            campaign.get("quests") or {},
            campaign.get("difficulty", "medium"),
            campaign.get("world_baseline"),
        ),
        global_summary=context.get("global_summary") or "",
        summary_context=context.get("summary_context") or "",
        recall=context.get("recall") or {},
        history=data.get("history") or [],
        stimuli=stimuli,
        derived=bool(data["meta"].get("derived")),
        reconstructed=bool(data["meta"].get("reconstructed")),
        notes=str(data["meta"].get("notes") or ""),
    )
