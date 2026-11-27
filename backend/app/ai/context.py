from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.dm import DMPromptContext, render_dm_prompt
from app.ai.recalled_memories import recall_facts
from app.memory.context_snapshot import TurnContextSnapshot
from app.memory.recall import PreparedRecallQuery


class ContextMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


@dataclass
class GameContext:
    system_prompt: str = ""
    messages: list[ContextMessage] = field(default_factory=list)
    importance_score: int = 5
    prompt_context: DMPromptContext = DMPromptContext()


def _active_tools(world_state: dict) -> set[str]:
    from app.ai.tools.tool_groups import resolve_active_tools_from_state

    return resolve_active_tools_from_state(world_state)


async def build_context(
    snapshot: TurnContextSnapshot,
    player_action: str,
    db: AsyncSession,
    query_embedding: PreparedRecallQuery | None = None,
) -> GameContext:
    """Build the DM prompt from the claim-time context snapshot."""
    recalled = await recall_facts(snapshot, player_action, db, query_embedding)
    prompt_context = replace(snapshot.prompt, recalled_memories=recalled)
    system_prompt = render_dm_prompt(
        snapshot.scene,
        prompt_context,
        _active_tools(snapshot.scene.world_state),
    )
    messages: list[ContextMessage] = [
        {"role": message.role, "content": message.content} for message in snapshot.history
    ]
    messages.append({"role": "user", "content": player_action})
    return GameContext(
        system_prompt=system_prompt,
        messages=messages,
        prompt_context=prompt_context,
    )
