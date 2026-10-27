"""LangGraph state definition for the DM agent turn."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

from app.ai.prompts.dm import DMPromptContext
from app.models.quest import QuestRegistry


class GameState(TypedDict):
    # ── Input ────────────────────────────────────────────────────────────────
    player_action: str
    campaign_id: str
    user_id: str

    # ── LLM conversation (append-only via add_messages reducer) ─────────────
    messages: Annotated[list, add_messages]

    # ── Mutable world state ──────────────────────────────────────────────────
    world_state: dict[str, Any]
    char_data: dict[str, Any]
    # Campaign-owned quest registry (ADR 0019 A1) — status is the containing list
    quests: QuestRegistry
    # Frozen authored world tree (ADR 0008 C11) — read-only, never written back
    world_baseline: dict[str, Any]
    # Campaign difficulty (ADR 0003 B8) — governs the death policy only
    difficulty: str

    # ── Turn output (accumulated across steps) ───────────────────────────────
    narration: str
    narration_segments: list[dict[str, Any]]  # [{step, text, dice, npc_dialogues}]
    scene_mood: str
    tool_events: list[dict[str, Any]]
    dice_results: list[dict[str, Any]]  # pre-rolled, sent to frontend as-is
    npc_dialogues: list[dict[str, Any]]  # [{npc_name, dialogue, action}]
    called_npcs: list[str]  # dedup: NPC names already invoked this turn
    time_passed_minutes: int

    # ── Metadata ─────────────────────────────────────────────────────────────
    model_used: str
    importance_score: int

    # ── Control flow ─────────────────────────────────────────────────────────
    step_count: int
    max_agent_steps: int
    consecutive_empty_steps: int  # steps without state changes or fresh playable results
    progress_fingerprints: list[str]
    allowed_tools: list[str]
    closing_step: bool
    followup_required: bool
    death_event: dict[str, Any] | None

    # ── Internal (set by context_node, consumed by dm_node) ──────────────────
    system_prompt: str
    prompt_context: DMPromptContext
    model_config: dict[str, Any]  # {provider, model, max_tokens}
