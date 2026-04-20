"""Shared types for agentic AI provider responses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class AgentResponse:
    """Complete response from a single LLM step in the agentic loop."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class TextChunk:
    text: str


@dataclass
class ToolCallChunk:
    tool_call: ToolCall


# Union type for streaming chunks
AgentChunk = TextChunk | ToolCallChunk
