from __future__ import annotations

import os
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid5

from httpx import AsyncClient
from sqlalchemy import select

from app import dependencies
from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentResponse, ToolCall
from app.ai.router import ModelConfig
from app.memory.batch_source_contracts import BatchInput
from app.models.memory_job import MemoryJob
from app.schemas.campaign import TurnResponse, TurnSubmit
from eval.integrated_memory.source_evidence import OperationEvidence, PersistedTurnEvidence
from eval.memory_scenarios.build import initial_world
from eval.memory_scenarios.chapters import PLAYER_NAME
from eval.memory_scenarios.timeline import CHAPTERS

_REQUEST_NAMESPACE = UUID("9d584f93-e7e5-4f24-992d-06d6a697f161")


async def create_replay_campaign(
    client: AsyncClient, *, name: str = "Integrated memory replay", language: str = "en"
) -> UUID:
    from app.services import campaign_service

    baseline, world_state, quests, _ = initial_world()
    with patch.object(
        campaign_service,
        "instantiate_world",
        return_value=(baseline, world_state, quests),
    ):
        response = await client.post(
            "/api/campaigns",
            json={
                "world_id": "the-awakening",
                "name": name,
                "difficulty": "medium",
                "language": language,
                "character_data": {
                    "name": PLAYER_NAME,
                    "hp": {"current": 20, "max": 20},
                    "abilities": {"dexterity": 2},
                    "inventory": [],
                },
            },
        )
    response.raise_for_status()
    return UUID(response.json()["id"])


@asynccontextmanager
async def authored_boundaries(sources: BatchInput) -> AsyncIterator[None]:
    from app.ai.npc_outcomes import NPCSilent, NPCSpeaking
    from app.api.rate_limit import limiter
    from app.core.dm import dm_graph, dm_nodes, npc_beat
    from app.memory import embedding_worker, job_lifecycle, recall

    if any(
        task is not None and not task.done()
        for task in (job_lifecycle._task, embedding_worker._task)
    ):
        raise RuntimeError("integrated replay refuses to run alongside background workers")
    async with dependencies.async_session() as db:
        running = await db.scalar(select(MemoryJob.id).where(MemoryJob.state == "running"))
    if running is not None:
        raise RuntimeError("integrated replay refuses to start while a memory worker is running")

    current_index = 0
    npc_name = initial_world()[3]

    def select_action(messages: list[dict[str, object]]) -> None:
        nonlocal current_index
        for message in reversed(messages):
            action = message.get("content")
            if isinstance(action, str):
                match = next(
                    (
                        index
                        for index, turn in enumerate(sources.turns)
                        if turn.player_action == action
                    ),
                    None,
                )
                if match is not None:
                    current_index = match
                    return

    class OfflineProvider:
        calls_by_index: dict[int, int] = {}

        async def generate_with_tools(self, **kwargs: object) -> AgentResponse:
            select_action(cast(list[dict[str, object]], kwargs["messages"]))
            index = current_index
            count = self.calls_by_index.get(index, 0)
            self.calls_by_index[index] = count + 1
            if count:
                return AgentResponse(text="")
            chapter = CHAPTERS[index]
            npc = npc_name
            calls = [
                ToolCall(
                    id=f"replay-{index + 1}-{ordinal}",
                    name=call.name,
                    arguments={
                        key: value.format(npc=npc, player=PLAYER_NAME)
                        if isinstance(value, str)
                        else value
                        for key, value in call.arguments.items()
                    },
                )
                for ordinal, call in enumerate(chapter.calls, start=1)
            ]
            return AgentResponse(
                text=chapter.narration.format(npc=npc, player=PLAYER_NAME), tool_calls=calls
            )

    provider = OfflineProvider()
    model = ModelConfig(provider="local", model="integrated-replay", max_tokens=500)

    async def resolve(_: object) -> tuple[AIProvider, ModelConfig]:
        return cast(AIProvider, provider), model

    async def no_recall(*_: object, **__: object) -> None:
        return None

    async def npc_result(actors: list[object], *_: object) -> list[object]:
        speaking = NPCSpeaking(npc_name, ("The original was kept beneath the ferry ledger.",))
        silent = NPCSilent(npc_name, ())
        chapter = CHAPTERS[current_index]
        result = silent if chapter is not None and chapter.npc == "silent" else speaking
        return [result for _ in actors]

    tools_callable = dm_graph.dm_graph.nodes["tools_node"].bound
    original_tools = tools_callable.afunc

    async def seeded_tools(state: object, config: object = None) -> object:
        random.seed(current_index + 1)
        return await original_tools(state)

    with (
        patch.object(dm_nodes, "get_user_generation", resolve),
        patch.object(npc_beat, "invoke_npcs_parallel", npc_result),
        patch.object(recall, "embed_recall_query", no_recall),
        patch.object(tools_callable, "afunc", seeded_tools),
        patch.object(limiter, "enabled", False),
    ):
        yield


async def replay_sources(
    client: AsyncClient,
    campaign_id: UUID,
    sources: BatchInput,
    *,
    after_turn: Callable[[], Awaitable[None]],
    evidence_path: Path | None = None,
) -> tuple[PersistedTurnEvidence, ...]:
    evidence: list[PersistedTurnEvidence] = []
    expected_head: UUID | None = None
    expected_epoch = 0

    for index, source in enumerate(sources.turns, start=1):
        request_id = uuid5(_REQUEST_NAMESPACE, f"{campaign_id}:{source.turn_id}")
        submission = TurnSubmit(
            action=source.player_action,
            request_id=request_id,
            expected_head_turn_id=expected_head,
            expected_context_epoch=expected_epoch,
        )
        previous_rng = random.getstate()
        random.seed(index)
        try:
            response = await client.post(
                f"/api/campaigns/{campaign_id}/action", json=submission.model_dump(mode="json")
            )
        finally:
            random.setstate(previous_rng)
        if response.is_error:
            raise AssertionError(f"replay failed for {source.turn_id}: {response.text}")
        turn = TurnResponse.model_validate(response.json())
        turn_evidence = PersistedTurnEvidence(
            source_turn_id=source.turn_id,
            turn_id=turn.turn_id,
            request_id=request_id,
            head_turn_id=turn.head_turn_id,
            context_epoch=turn.context_epoch,
            operations=(),
        )
        try:
            if turn.request_id != request_id or turn.player_action != source.player_action:
                raise AssertionError(f"API response diverged at source turn {source.turn_id}")
            from app.memory.batch_input import load_turn_input

            async with dependencies.async_session() as db:
                persisted = (await load_turn_input(db, campaign_id, (turn.turn_id,))).turns[0]
            if persisted.narration != source.narration:
                raise AssertionError(
                    f"persisted narration diverged at source turn {source.turn_id}"
                )
            expected_ops = tuple(
                operation.model_dump(mode="json", exclude={"id"})
                for operation in (source.operations or ())
            )
            actual_ops = tuple(
                operation.model_dump(mode="json", exclude={"id"})
                for operation in (persisted.operations or ())
            )
            if actual_ops != expected_ops:
                raise AssertionError(
                    f"persisted operations diverged at source turn {source.turn_id}: "
                    f"expected={expected_ops!r}; actual={actual_ops!r}"
                )
            if len(persisted.operations or ()) != len(source.operations or ()):
                raise AssertionError(
                    f"persisted operation IDs diverged at source turn {source.turn_id}"
                )
            turn_evidence = turn_evidence.model_copy(
                update={
                    "operations": tuple(
                        OperationEvidence(
                            source_operation_id=operation.id,
                            operation_id=actual.id,
                            turn_id=turn.turn_id,
                        )
                        for operation, actual in zip(
                            source.operations or (), persisted.operations or (), strict=True
                        )
                    )
                }
            )
        except Exception as exc:
            turn_evidence = turn_evidence.model_copy(
                update={"status": "invalid", "diagnostic": str(exc)}
            )
            _append_turn_evidence(evidence_path, turn_evidence)
            evidence.append(turn_evidence)
            raise
        _append_turn_evidence(evidence_path, turn_evidence)
        evidence.append(turn_evidence)
        expected_head = turn.head_turn_id
        expected_epoch = turn.context_epoch
        await after_turn()
    return tuple(evidence)


def _append_turn_evidence(path: Path | None, evidence: PersistedTurnEvidence) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(evidence.model_dump_json() + "\n")
        stream.flush()
        os.fsync(stream.fileno())
