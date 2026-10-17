"""Shared types for agentic AI provider responses."""

from __future__ import annotations

from dataclasses import dataclass, field

# Google returns an opaque thought_signature on function-call parts and expects it
# echoed back on the next request. It rides message entries under this key, which
# OpenAI-compatible providers must strip before hitting their SDK (see openai_compat).
TOOL_CALL_SIGNATURES_KEY = "tool_call_signatures"
# Gemini 2.5 may put the signature on the first part whatever its type, so a text
# part can carry one too; it rides message entries under this second key.
TEXT_SIGNATURE_KEY = "text_thought_signature"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
    signature: bytes | None = None


@dataclass
class AgentResponse:
    """Complete response from a single LLM step in the agentic loop."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    text_signature: bytes | None = None


@dataclass
class TextChunk:
    text: str


@dataclass
class ToolCallChunk:
    tool_call: ToolCall


# Union type for streaming chunks
AgentChunk = TextChunk | ToolCallChunk
