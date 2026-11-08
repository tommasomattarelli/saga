from typing import cast
from unittest.mock import patch
from uuid import UUID

from langchain_core.messages import AIMessage
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.ai.npc_director import NPCInput
from app.ai.npc_outcomes import NPCResult, NPCSpeaking
from app.ai.providers.openai_compat import strip_provider_metadata
from app.ai.router import get_gameplay_config
from app.ai.tools.dm_tools import get_tool_schemas
from app.core.dm.dm_helpers import messages_to_raw
from app.core.dm.dm_nodes import step_system_prompt
from app.core.dm.dm_tools_executor import tools_node
from app.core.dm.game_state import GameState
from app.core.dm.loop_policy import closing_step, step_tools
from eval.dialogue.cases import scenario_for
from eval.dialogue.pipeline import apply_update, initial_state


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str
    messages: list[dict[str, JsonValue]]
    tools: list[dict[str, JsonValue]]
    model: str
    max_tokens: int = Field(gt=0, le=1024)

    def wire_messages(self) -> list[ChatCompletionMessageParam]:
        return cast(
            list[ChatCompletionMessageParam],
            [
                {"role": "system", "content": self.system_prompt},
                *strip_provider_metadata(self.messages),
            ],
        )

    def wire_tools(self) -> list[ChatCompletionToolParam]:
        return cast(list[ChatCompletionToolParam], self.tools)

    def body(self) -> dict[str, JsonValue]:
        return {
            "model": self.model,
            "messages": cast(JsonValue, self.wire_messages()),
            "tools": cast(JsonValue, self.wire_tools()),
            "tool_choice": "auto",
            "max_tokens": self.max_tokens,
        }


def _request(state: GameState, model: str, max_tokens: int) -> Payload:
    closing = closing_step(state)
    allowed = step_tools(state["world_state"], closing=closing)
    return Payload(
        system_prompt=step_system_prompt(state, allowed, closing),
        messages=messages_to_raw(state["messages"]),
        tools=get_tool_schemas(allowed),
        model=model,
        max_tokens=max_tokens,
    )


async def build_payloads(model: str, max_tokens: int) -> dict[str, Payload]:
    scenario = scenario_for("npc_speaks")
    state = initial_state(scenario, UUID(int=0))
    state["max_agent_steps"] = get_gameplay_config().max_agent_steps
    first = _request(state, model, max_tokens)
    stimulus = scenario.stimuli["npc_followup"]

    async def actor(actors: list[NPCInput], owner: UUID) -> list[NPCResult]:
        if len(actors) != 1 or actors[0].npc_name != stimulus.npc_name:
            raise ValueError("Cache replay must resolve exactly the fixture's existing NPC.")
        return [NPCSpeaking(stimulus.npc_name, (stimulus.npc_dialogue,), stimulus.npc_action)]

    state["messages"].append(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "cache-probe-npc",
                    "type": "tool_call",
                    "name": "invoke_npc",
                    "args": {"name": stimulus.npc_name, "context": stimulus.npc_context},
                }
            ],
        )
    )
    state["step_count"] = 1
    state["allowed_tools"] = sorted(step_tools(state["world_state"], closing=False))
    # The real executor derives markers, NPC history and reminders from a fixed actor result.
    with patch("app.core.dm.npc_beat.invoke_npcs_parallel", actor):
        apply_update(state, await tools_node(state))
    if len(state["npc_lines"]) != 1:
        raise ValueError("Cache replay did not produce the expected NPC line.")
    return {"A": first, "B": _request(state, model, max_tokens)}
