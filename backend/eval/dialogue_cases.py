"""Controlled dialogue cases over the captured Thornhaven evaluation state."""

from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import dataclass
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from scenario import Scenario, load

from app.ai.tools.tools_npc import UpdateNpc


@dataclass(frozen=True)
class Case:
    name: str
    ceiling: int
    expected_relevance: bool = False
    nominal: int | None = None
    expected_initial_npcs: frozenset[str] = frozenset()
    expected_second_npc: str | None = None
    followup_actions: tuple[str, ...] = ()


CASES = (
    Case("npc_speaks", 1),
    Case("npc_followup", 1),
    Case("actor_en", 1),
    Case("actor_it", 1),
    Case("actor_silent", 1),
    Case(
        "two_npc_two_beat",
        7,
        nominal=6,
        expected_initial_npcs=frozenset({"aldric", "mira"}),
        expected_second_npc="aldric",
    ),
    Case("npc_followup_short", 1),
    Case("actor_scene", 1),
    Case(
        "two_npc_natural",
        7,
        expected_relevance=True,
        nominal=6,
    ),
    Case(
        "two_npc_conversation",
        14,
        expected_relevance=True,
        nominal=12,
        followup_actions=(
            "I lower my voice and ask whether that changes what we should do next, without leaving the square.",
        ),
    ),
)

_BY_NAME = {case.name: case for case in CASES}


def scenario_for(case_name: str) -> Scenario:
    """Return an isolated dialogue case on the saturated captured baseline."""
    if case_name not in _BY_NAME:
        raise ValueError(f"unknown dialogue case: {case_name}")

    sc = load("debug-thornhaven")
    sc.campaign.world_state = deepcopy(sc.campaign.world_state)
    sc.campaign.character_data = deepcopy(sc.campaign.character_data)
    sc.campaign.quests = deepcopy(sc.campaign.quests)
    sc.campaign.world_baseline = deepcopy(sc.campaign.world_baseline)
    sc.history = deepcopy(sc.history)
    sc.stimuli = deepcopy(sc.stimuli)
    sc.recall = deepcopy(sc.recall)
    sc.name = f"pr2-case-{case_name}"
    sc.notes = f"controlled overlay on reconstructed debug-thornhaven capture; case={case_name}."

    if case_name in {"npc_speaks", "npc_followup", "actor_scene"}:
        sc.stimuli["npc_speaks"].player = "Aldric, do you know who I am? Have you seen me before?"
    elif case_name in {"npc_followup_short"}:
        sc.stimuli["npc_speaks"].player = "Aldric, is the north gate open?"
        sc.stimuli["npc_followup"] = deepcopy(sc.stimuli["npc_followup"])
        sc.stimuli["npc_followup"].player = sc.stimuli["npc_speaks"].player
        sc.stimuli["npc_followup"].npc_dialogue = "No."
    elif case_name == "actor_en":
        sc.language = sc.campaign.language = "en"
        sc.stimuli["npc_speaks"].player = "Aldric, sai chi sono? Mi hai già visto prima?"
    elif case_name == "actor_it":
        sc.language = sc.campaign.language = "it"
        sc.stimuli["npc_speaks"].player = "Aldric, do you know who I am? Have you seen me before?"
    elif case_name == "actor_silent":
        present = _present_npcs(sc)
        first = next(iter(present.values()))
        first.setdefault("traits", {})["personality"] = (
            "Has taken a vow of silence and communicates only through gestures; "
            "a quiet warning makes clear this vow is deliberate."
        )
        sc.stimuli["npc_speaks"].player = "Aldric, do you know who I am? Have you seen me before?"
    elif case_name in {"two_npc_two_beat", "two_npc_natural", "two_npc_conversation"}:
        _configure_two_npc_case(sc)
        if case_name in {"two_npc_natural", "two_npc_conversation"}:
            sc.stimuli["npc_speaks"].player = (
                "I show the broken courier seal to Aldric and Mira. "
                "'I found this on the north road. Something is wrong with this delivery.' "
                "I watch their reactions."
            )
            sc.language = sc.campaign.language = "en"

    return sc


def case_for_scenario_name(name: str) -> Case:
    prefix = "pr2-case-"
    case_name = name.removeprefix(prefix) if name.startswith(prefix) else name
    try:
        return _BY_NAME[case_name]
    except KeyError as exc:
        raise ValueError(f"unknown dialogue case: {case_name}") from exc


def _present_npcs(sc: Scenario) -> dict:
    world = sc.campaign.world_state
    location = world.get("meta", {}).get("current_location")
    return {
        key: npc
        for key, npc in world.get("npcs", {}).items()
        if npc.get("lifecycle") == "alive" and npc.get("location") == location
    }


def _configure_two_npc_case(sc: Scenario) -> None:
    world = sc.campaign.world_state
    for key, npc in list(world.get("npcs", {}).items()):
        if npc.get("name") != "Aldric":
            world["npcs"].pop(key)

    with (
        patch("app.ai.tools.tools_npc.uuid4", return_value=uuid5(NAMESPACE_URL, "saga-pr2-mira")),
        patch("app.core.npc_classes.random", random.Random(0)),
    ):
        result = UpdateNpc(
            name="Mira",
            create=True,
            updates={
                "location": "Thornhaven",
                "role": "Village courier",
                "personality": "Observant, candid, and cautious with strangers.",
            },
        ).execute_with_baseline(world, sc.campaign.character_data, sc.campaign.world_baseline)
    if "created" not in result.description:
        raise RuntimeError(f"could not create dialogue-case NPC: {result.description}")

    sc.language = sc.campaign.language = "it"
    sc.stimuli["npc_speaks"].player = (
        "Aldric and Mira, tell me independently what you each know about the old mines. "
        "Then Aldric, respond specifically to what Mira said."
    )


__all__ = ["CASES", "Case", "case_for_scenario_name", "scenario_for"]
