import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from unittest.mock import patch

from app.ai.generation_context import Generation
from app.ai.npc_director import NPCInput
from app.ai.npc_outcomes import NPCResult

type ActorObserver = Callable[[list[NPCInput], uuid.UUID], Awaitable[list[NPCResult]]]


@dataclass(frozen=True)
class PipelineContext:
    generation: Generation
    observer: ActorObserver


_pipeline: ContextVar[PipelineContext] = ContextVar("evaluation_pipeline")


async def _generation(owner: uuid.UUID | str) -> Generation:
    return _pipeline.get().generation


async def _observe(actors: list[NPCInput], owner: uuid.UUID) -> list[NPCResult]:
    return await _pipeline.get().observer(actors, owner)


@contextmanager
def evaluation_dispatch() -> Iterator[None]:
    with (
        patch("app.core.dm.dm_nodes.get_user_generation", _generation),
        patch("app.ai.generation_context.get_user_generation", _generation),
        patch("app.core.dm.npc_beat.invoke_npcs_parallel", _observe),
    ):
        yield


@contextmanager
def pipeline_context(generation: Generation, observer: ActorObserver) -> Iterator[None]:
    token = _pipeline.set(PipelineContext(generation, observer))
    try:
        yield
    finally:
        _pipeline.reset(token)
