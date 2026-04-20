"""Pure helper functions for the DM graph — message conversion and segment management."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def tool_calls_from_ai_message(msg: AIMessage) -> list[dict]:
    tcs = getattr(msg, "tool_calls", None) or []
    return list(tcs)


def last_ai_message(messages: list) -> AIMessage | None:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return msg
    return None


def raw_history_to_lc(messages: list[dict]) -> list:
    lc: list = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content") or ""
        if role == "user":
            lc.append(HumanMessage(content=content))
        elif role == "assistant":
            lc.append(AIMessage(content=content))
    return lc


def messages_to_raw(messages: list) -> list[dict]:
    raw: list[dict] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            raw.append({"role": "user", "content": str(msg.content)})
        elif isinstance(msg, AIMessage):
            entry: dict = {"role": "assistant", "content": msg.content or None}
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"]),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            raw.append(entry)
        elif isinstance(msg, ToolMessage):
            raw.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "name": msg.name or msg.tool_call_id,
                    "content": str(msg.content),
                }
            )
        elif isinstance(msg, dict):
            raw.append(msg)
    return raw


def get_or_create_segment(segments: list[dict], step: int) -> dict:
    for seg in segments:
        if seg.get("step") == step:
            return seg
    seg = {"step": step, "text": "", "dice": None, "npc_dialogues": []}
    segments.append(seg)
    return seg


def sync_narration_to_segment(segments: list[dict], step: int, full_narration: str) -> None:
    seg = get_or_create_segment(segments, step)
    if not seg["text"] and full_narration:
        seg["text"] = full_narration
