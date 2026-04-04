"""Agentic DM turn loop — replaces streaming.py.

The DM narrates freely in text and calls typed tools to act on the world.
The loop runs up to MAX_AGENT_STEPS rounds; each round the LLM can emit
narration + zero-or-more tool calls. Tool results are fed back and the loop
continues until no tool calls are emitted or the step limit is reached.

Special tools handled inline:
- request_dice  → rolls server-side, pauses until player reveals, feeds outcome back
- invoke_npc    → calls npc_director, feeds dialogue back to DM
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import structlog

_llm_io = logging.getLogger("llm_io")
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_context
from app.ai.exceptions import ContentPolicyError
from app.ai.npc_director import invoke_npcs_parallel
from app.ai.providers.schemas import TextChunk, ToolCallChunk
from app.ai.router import AICallType, route_ai_call
from app.ai.semantic_resolver import resolve_player_action
from app.ai.tools.dm_tools import execute_tool, get_tool, get_tool_schemas
from app.config import settings
from app.core.death import check_player_death
from app.core.dice import ability_check
from app.core.engine import CONTENT_POLICY_NARRATION, StreamEvent
from app.memory.updater import apply_typed_updates
from app.memory.world_state import advance_game_clock, migrate_world_state
from app.models.campaign import Campaign, CampaignStatus

logger = structlog.get_logger()

_SPECIAL_TOOLS = frozenset({"request_dice", "invoke_npc"})


@dataclass
class _AgentState:
    world_state: dict
    char_data: dict
    narration: str = ""
    scene_mood: str = "neutral"
    tool_events: list[dict] = field(default_factory=list)
    time_passed_minutes: int = 0


class DmAgent:
    """Agentic DM executor. One instance per turn."""

    def __init__(self, campaign: Campaign, dice_reveal_event: asyncio.Event) -> None:
        self.campaign = campaign
        self.dice_reveal_event = dice_reveal_event
        self._provider = None  # set during run()

    async def run(self, player_action: str, db: AsyncSession) -> AsyncIterator[StreamEvent]:
        campaign = self.campaign

        resolver_output = await resolve_player_action(player_action, campaign, db)
        logger.debug(
            "semantic_resolver",
            target_npcs=resolver_output.target_npcs,
            target_locations=resolver_output.target_locations,
        )

        context = await build_context(campaign, player_action, db)
        model_config = await route_ai_call(AICallType.DM_NARRATION, context)

        logger.info(
            "ai_request",
            campaign_id=str(campaign.id),
            turn_number=campaign.turn_number,
            provider=model_config.provider,
            model=model_config.model,
            importance=context.importance_score,
            system_prompt_preview=context.system_prompt[:500],
            messages_count=len(context.messages),
        )

        from app.ai.providers.base import get_provider
        self._provider = get_provider(model_config.provider)

        state = _AgentState(
            world_state=migrate_world_state(campaign.world_state or {}),
            char_data=campaign.character_data or {},
        )
        messages = list(context.messages)
        tool_schemas = get_tool_schemas()

        empty_text_steps = 0
        for step in range(settings.saga_max_agent_steps):
            step_text, step_tool_calls, stop = "", [], False

            # Full tool schemas only on step 0; just names on subsequent steps
            tools_log = tool_schemas if step == 0 else [t["function"]["name"] for t in tool_schemas]
            _llm_io.info(json.dumps({
                "direction": "input",
                "campaign_id": str(campaign.id),
                "turn": campaign.turn_number,
                "step": step,
                "provider": model_config.provider,
                "model": model_config.model,
                "system_prompt": context.system_prompt if step == 0 else "(same as step 0)",
                "messages": messages,
                "tools": tools_log,
            }, ensure_ascii=False, indent=2) + "\n" + ("─" * 80))

            try:
                async for chunk in self._provider.stream_with_tools(
                    system_prompt=context.system_prompt,
                    messages=messages,
                    tools=tool_schemas,
                    model=model_config.model,
                    temperature=model_config.temperature,
                    max_tokens=model_config.max_tokens,
                ):
                    if isinstance(chunk, TextChunk):
                        yield StreamEvent(type="narration_chunk", data=chunk.text)
                        step_text += chunk.text
                        state.narration += chunk.text
                    elif isinstance(chunk, ToolCallChunk):
                        step_tool_calls.append(chunk.tool_call)
            except ContentPolicyError:
                yield StreamEvent(type="narration_chunk", data=CONTENT_POLICY_NARRATION)
                state.narration += CONTENT_POLICY_NARRATION
                stop = True

            _llm_io.info(json.dumps({
                "direction": "output",
                "campaign_id": str(campaign.id),
                "turn": campaign.turn_number,
                "step": step,
                "text": step_text,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in step_tool_calls
                ],
            }, ensure_ascii=False, indent=2) + "\n" + ("═" * 80))

            logger.info(
                "agent_step",
                step=step,
                text_len=len(step_text),
                tool_calls=[tc.name for tc in step_tool_calls],
            )
            # Mirror legacy ai_raw_response key for log monitoring
            logger.info(
                "ai_raw_response",
                step=step,
                raw_length=len(step_text),
                raw_preview=step_text[:300],
                tool_calls=[{"name": tc.name, "args": tc.arguments} for tc in step_tool_calls],
            )

            if stop or not step_tool_calls:
                break

            # Guard: if the model keeps calling tools without any narration,
            # stop after 2 consecutive empty-text steps to prevent degenerate loops.
            if not step_text:
                empty_text_steps += 1
                if empty_text_steps >= 2:
                    logger.warning("agent_empty_text_loop", step=step)
                    break
            else:
                empty_text_steps = 0

            # ── Execute tool calls, collect results ───────────────────────────
            tool_results: list[dict] = []  # messages to append (formatted per provider)

            # Split regular (parallel) from special (sequential)
            regular = [tc for tc in step_tool_calls if tc.name not in _SPECIAL_TOOLS]
            special = [tc for tc in step_tool_calls if tc.name in _SPECIAL_TOOLS]

            # Regular tools — execute in parallel
            if regular:
                results = await asyncio.gather(
                    *[self._run_regular(tc, state) for tc in regular], return_exceptions=True
                )
                for tc, res in zip(regular, results):
                    if isinstance(res, Exception):
                        logger.warning("tool_exec_failed", tool=tc.name, exc_info=res)
                        result_str = f"Tool {tc.name} failed: {res}"
                    else:
                        events, result_str = res
                        for ev in events:
                            yield ev
                    tool_results.append(
                        self._provider.format_tool_result(tc.id, tc.name, result_str)
                    )

            # Special tools — sequential (dice needs player input, NPC needs await)
            for tc in special:
                if tc.name == "request_dice":
                    events, result_str = await self._run_dice(tc, state)
                elif tc.name == "invoke_npc":
                    events, result_str = await self._run_npc(tc, state, db)
                else:
                    result_str = f"Unknown special tool: {tc.name}"
                    events = []
                for ev in events:
                    yield ev
                tool_results.append(
                    self._provider.format_tool_result(tc.id, tc.name, result_str)
                )

            _llm_io.info(json.dumps({
                "direction": "tool_results",
                "campaign_id": str(campaign.id),
                "turn": campaign.turn_number,
                "step": step,
                "results": tool_results,
            }, ensure_ascii=False, indent=2) + "\n" + ("─" * 80))

            # Build assistant + tool result messages for next step
            assistant_tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in step_tool_calls
            ]
            messages.append({
                "role": "assistant",
                "content": step_text or None,
                "tool_calls": assistant_tool_calls,
            })
            messages.extend(tool_results)

        # ── Post-loop cleanup ─────────────────────────────────────────────────
        if state.time_passed_minutes > 0:
            state.world_state = advance_game_clock(state.world_state, state.time_passed_minutes)

        death_mode = state.char_data.get("death_mode", "cronista")
        death_result = check_player_death(state.char_data, death_mode, state.world_state)

        if death_result.action != "alive":
            yield StreamEvent(
                type="death_event",
                data={
                    "is_dead": death_result.is_dead,
                    "action": death_result.action,
                    "death_mode": death_result.death_mode,
                    "narrative_instruction": death_result.narrative_instruction,
                    "destino_lives_remaining": death_result.destino_lives_remaining,
                },
            )
            if death_result.is_dead:
                campaign.status = CampaignStatus.COMPLETED

        yield StreamEvent(
            type="turn_result",
            data={
                "narration": state.narration,
                "world_state": state.world_state,
                "character_data": state.char_data,
                "scene_mood": state.scene_mood,
                "tool_events": state.tool_events,
                "time_passed_minutes": state.time_passed_minutes,
                "model_used": model_config.model,
                "importance_score": context.importance_score,
                "requires_player_action": True,
            },
        )

    async def _run_regular(
        self, tc, state: _AgentState
    ) -> tuple[list[StreamEvent], str]:
        """Execute a regular (non-special) tool. Returns (events_to_yield, result_str)."""
        result = execute_tool(tc.name, tc.arguments, state.world_state, state.char_data)
        state.world_state = result.world_state
        state.char_data = result.char_data

        events: list[StreamEvent] = []

        if tc.name == "set_scene_mood" and result.extra.get("mood"):
            state.scene_mood = result.extra["mood"]
            events.append(StreamEvent(type="scene_mood", data=result.extra["mood"]))

        if tc.name == "advance_time":
            state.time_passed_minutes += tc.arguments.get("minutes", 0)

        tool_cls = get_tool(tc.name)
        if tool_cls and tool_cls.visible():
            event_data = {
                "tool": tc.name,
                "args": tc.arguments,
                "result": result.description,
                "extra": result.extra,
            }
            state.tool_events.append(event_data)
            events.append(StreamEvent(type="tool_executed", data=event_data))

        return events, result.description

    async def _run_dice(
        self, tc, state: _AgentState
    ) -> tuple[list[StreamEvent], str]:
        """Handle request_dice. Pauses until player clicks reveal."""
        args = tc.arguments
        check = args.get("check", "check")
        dc = int(args.get("dc", 10))
        stat = args.get("stat", "DEX")
        reason = args.get("reason", "")

        abilities = state.char_data.get("abilities", {})
        stat_score = abilities.get(stat, abilities.get(stat.lower(), 10))
        modifier = (stat_score - 10) // 2

        dice_result = ability_check(modifier=modifier, dc=dc)
        dice_result["check"] = check
        dice_result["stat"] = stat
        dice_result["reason"] = reason

        events: list[StreamEvent] = [
            StreamEvent(type="dice_roll", data=dice_result),
            StreamEvent(type="await_player", data="dice_reveal"),
        ]

        # Pause until WebSocket receives "dice_revealed" from client
        self.dice_reveal_event.clear()
        await self.dice_reveal_event.wait()

        outcome = dice_result.get("outcome", "partial_success")
        total = dice_result.get("total", 10)
        result_str = (
            f"{check.title()} check (DC {dc}): rolled {total} ({modifier:+d} modifier) → {outcome}."
            + (f" Context: {reason}" if reason else "")
        )
        return events, result_str

    async def _run_npc(
        self, tc, state: _AgentState, db: AsyncSession
    ) -> tuple[list[StreamEvent], str]:
        """Handle invoke_npc. Calls NPC director and returns dialogue to DM."""
        npc_name = tc.arguments.get("name", "")
        context_hint = tc.arguments.get("context", "")

        npc_results = await invoke_npcs_parallel(
            npc_names=[npc_name],
            campaign=self.campaign,
            player_action=context_hint,
            dm_narration=state.narration[-500:] if state.narration else "",
        )

        events: list[StreamEvent] = []
        dialogue_parts: list[str] = []

        for npc in npc_results:
            event_data = {
                "npc_name": npc.npc_name,
                "dialogue": npc.dialogue,
                "action": npc.action,
            }
            events.append(StreamEvent(type="npc_dialogue", data=event_data))
            part = f'{npc.npc_name}: "{npc.dialogue}"'
            if npc.action:
                part += f" [{npc.action}]"
            dialogue_parts.append(part)

            if npc.disposition_change != 0:
                new_state, new_char = apply_typed_updates(
                    state.world_state,
                    state.char_data,
                    [{"key": "npc_disposition", "target": npc.npc_name, "change": npc.disposition_change}],
                )
                state.world_state = new_state
                state.char_data = new_char

        result_str = " | ".join(dialogue_parts) if dialogue_parts else f"{npc_name} does not respond."
        return events, result_str
