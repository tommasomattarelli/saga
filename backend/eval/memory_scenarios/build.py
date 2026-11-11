from __future__ import annotations

import argparse
import asyncio
import json
import random
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid5

from langchain_core.messages import AIMessage
from pydantic import JsonValue

from app.ai.npc_outcomes import NPCSilent, NPCSpeaking
from app.core import world_instantiation
from app.core.dm.dm_nodes import post_process_node
from app.core.dm.dm_tools_executor import tools_node
from app.core.dm.game_state import GameState
from app.core.world_loader import load_world
from app.memory.batch_source_contracts import BatchInput, BatchTurnSource
from app.memory.operation_contracts import RecordedOperation
from app.memory.source_projection import project_operations
from app.models.quest import QuestRegistry
from eval.memory_scenarios.annotations import build_annotations
from eval.memory_scenarios.artifacts import write_scenario
from eval.memory_scenarios.chapters import PLAYER_NAME, Chapter
from eval.memory_scenarios.contracts import BuiltScenario
from eval.memory_scenarios.planning import batch_plan
from eval.memory_scenarios.timeline import CHAPTERS

ROOT = Path(__file__).resolve().parents[3]
NAMESPACE = UUID("1f97a84f-8db7-481b-9c68-b02ad3168fbb")
CAMPAIGN_ID = str(uuid5(NAMESPACE, "campaign"))
PLAYER_ID = str(uuid5(NAMESPACE, "fixture-player"))


def _calls(chapter: Chapter, turn: int, npc_name: str) -> list[dict[str, object]]:
    return [
        {
            "name": call.name,
            "args": {
                key: value.format(npc=npc_name, player=PLAYER_NAME)
                if isinstance(value, str)
                else value
                for key, value in call.arguments.items()
            },
            "id": f"turn-{turn}-call-{number}",
            "type": "tool_call",
        }
        for number, call in enumerate(chapter.calls, start=1)
    ]


@contextmanager
def _seeded_rng(seed: int) -> Iterator[None]:
    previous = random.getstate()
    random.seed(seed)
    try:
        yield
    finally:
        random.setstate(previous)


async def _run_turn(
    *,
    index: int,
    chapter: Chapter,
    world_state: dict[str, object],
    char_data: dict[str, object],
    quests: QuestRegistry,
    baseline: dict[str, object],
    npc_name: str,
) -> tuple[GameState, list[RecordedOperation]]:
    tool_calls = _calls(chapter, index, npc_name)
    state = cast(
        GameState,
        {
            "messages": [AIMessage(content="", tool_calls=tool_calls)] if tool_calls else [],
            "world_state": world_state,
            "char_data": char_data,
            "quests": quests,
            "world_baseline": baseline,
            "difficulty": "medium",
            "player_action": chapter.action.format(npc=npc_name, player=PLAYER_NAME),
            "campaign_id": CAMPAIGN_ID,
            "user_id": PLAYER_ID,
            "narration": "",
            "narration_segments": [
                {"step": 0, "text": chapter.narration.format(npc=npc_name, player=PLAYER_NAME)}
            ],
            "narrative_observations": [],
            "npc_beats": [],
            "npc_lines": [],
            "scene_mood": "neutral",
            "tool_events": [],
            "operations": [],
            "dice_results": [],
            "time_passed_minutes": 0,
            "model_used": "offline-fixture",
            "importance_score": 0,
            "step_count": 1,
            "max_agent_steps": 4,
            "consecutive_empty_steps": 0,
            "progress_fingerprints": [],
            "allowed_tools": [
                "update_quest",
                "move_to",
                "request_dice",
                "change_npc_psychology",
                "invoke_npc",
            ],
            "closing_step": False,
            "followup_required": False,
            "death_event": None,
            "system_prompt": "",
            "model_config": {},
        },
    )
    actor_results = {
        "silent": [NPCSilent(npc_name, ())],
        "speaking": [NPCSpeaking(npc_name, ("The original was kept beneath the ferry ledger.",))],
    }
    with _seeded_rng(index):
        if tool_calls:
            with patch(
                "app.core.dm.npc_beat.invoke_npcs_parallel",
                autospec=True,
                return_value=actor_results.get(chapter.npc or "", actor_results["speaking"]),
            ):
                state = cast(GameState, {**state, **(await tools_node(state))})
        state = cast(GameState, {**state, **post_process_node(state)})
    operations = state.get("operations", [])
    stable = [
        operation.model_copy(update={"id": uuid5(NAMESPACE, f"{index}:operation:{ordinal}")})
        for ordinal, operation in enumerate(operations, start=1)
    ]
    return state, stable


def _batch(turns: tuple[BatchTurnSource, ...]) -> BatchInput:
    local = tuple(
        turn.model_copy(update={"reference": f"t{index}"})
        for index, turn in enumerate(turns, start=1)
    )
    return BatchInput(turns=local)


def build_scenario(
    *,
    batch_size: int,
    plan: tuple[int, int, int] | None = None,
) -> BuiltScenario:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    asset = load_world(ROOT / "worlds" / "the-awakening")
    counter = 0

    def seeded_uuid() -> UUID:
        nonlocal counter
        counter += 1
        return uuid5(NAMESPACE, f"world-node:{counter}")

    with patch.object(world_instantiation, "uuid4", side_effect=seeded_uuid):
        baseline, world_state, quest_data = world_instantiation.instantiate_world(asset)
    start = world_state["meta"]["current_location"]
    npc_name = next(
        npc["name"] for npc in world_state["npcs"].values() if npc.get("location") == start
    )
    char_data: dict[str, object] = {
        "name": PLAYER_NAME,
        "hp": {"current": 20, "max": 20},
        "abilities": {"dexterity": 2},
        "inventory": [],
    }
    quests = QuestRegistry.model_validate(quest_data)
    turns: list[BatchTurnSource] = []
    annotations: list[JsonValue] = []
    for index, chapter in enumerate(CHAPTERS, start=1):
        state, operations = asyncio.run(
            _run_turn(
                index=index,
                chapter=chapter,
                world_state=world_state,
                char_data=char_data,
                quests=quests,
                baseline=baseline,
                npc_name=npc_name,
            )
        )
        world_state = state["world_state"]
        char_data = state["char_data"]
        quests = state["quests"]
        turns.append(
            BatchTurnSource(
                reference=f"t{index}",
                turn_id=uuid5(NAMESPACE, f"turn:{index}"),
                player_action=chapter.action.format(npc=npc_name, player=PLAYER_NAME),
                narration=state["narration"],
                operations=project_operations(tuple(operations)),
            )
        )
        annotations.append(
            cast(
                JsonValue,
                {"turn": index, "chapter": chapter.key, "expectations": list(chapter.expects)},
            )
        )
    source = BatchInput(turns=tuple(turns))
    complete = len(turns) // batch_size
    batches = tuple(
        _batch(tuple(turns[start : start + batch_size]))
        for start in range(0, complete * batch_size, batch_size)
    )
    tail_turns = tuple(turns[complete * batch_size :])
    tail = _batch(tail_turns) if tail_turns else None
    measured = (
        batch_plan(
            raw_turns=plan[0],
            intermediate_limit=plan[1],
            global_updates=plan[2],
            batch_size=batch_size,
            available_turns=len(turns),
            resolution_turn=next(
                index
                for index, chapter in enumerate(CHAPTERS, start=1)
                if chapter.key == "fulfilment"
            ),
        )
        if plan
        else None
    )
    return BuiltScenario(
        sources=source,
        annotations=build_annotations(annotations, npc_name),
        batches=batches,
        tail=tail,
        plan=measured,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a synthetic offline memory source fixture."
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, required=True)
    parser.add_argument("--raw-turns", type=int, required=True)
    parser.add_argument("--intermediate-limit", type=int, required=True)
    parser.add_argument("--global-updates", type=int, required=True)
    args = parser.parse_args()
    result = build_scenario(
        batch_size=args.batch_size,
        plan=(args.raw_turns, args.intermediate_limit, args.global_updates),
    )
    write_scenario(result, args.out)
    print(
        json.dumps(
            {
                "turns": len(result.sources.turns),
                "batches": len(result.batches),
                "tail_turns": len(result.tail.turns) if result.tail else 0,
                "plan": result.plan,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
