from __future__ import annotations

import json
import re

INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions|prompts)",
    r"you\s+are\s+now\s+",
    r"system\s*:\s*",
    r"<\|im_start\|>",
    r"\[INST\]",
    r"###\s*(instruction|system)",
    r"<\s*/?\s*system\s*>",  # XML-style system tags
    r"--\s*system\s*--",  # Markdown-style system delimiters
]

_compiled = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```")


_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.IGNORECASE | re.DOTALL)
_OPEN_THINK_RE = re.compile(r"<think\b[^>]*>.*\Z", re.IGNORECASE | re.DOTALL)


def strip_code_fences(raw: str) -> str:
    """Strip a leading/trailing markdown code fence from LLM output."""
    match = _FENCE_RE.search(raw)
    return match.group(1).strip() if match else raw.strip()


def strip_reasoning(raw: str) -> str:
    """Drop `<think>` blocks so deliberation never reaches a stored answer (#78).

    An unclosed block means the model was cut off mid-thought, so everything after
    the opening tag is reasoning too.
    """
    return _OPEN_THINK_RE.sub("", _THINK_RE.sub("", raw)).strip()


def parse_json_payload(raw: str) -> dict | list | None:
    """LLM output to JSON, tolerating code fences and mild malformation.

    `None` means the response could not be read as JSON at all — which is how
    reasoning prose surfaces as a failure instead of being stored as an answer.
    """
    cleaned = strip_code_fences(strip_reasoning(raw))
    if not cleaned:
        return None
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        from json_repair import repair_json

        try:
            parsed = json.loads(repair_json(cleaned))
        except (json.JSONDecodeError, ValueError):
            return None
    return parsed if isinstance(parsed, dict | list) and parsed else None


def sanitize_player_input(text: str) -> str:
    """Sanitize player input to prevent injection (max 2000 chars)."""
    sanitized = text.strip()
    sanitized = sanitized.replace("\x00", "")
    if len(sanitized) > 2000:
        sanitized = sanitized[:2000]
    return sanitized


def detect_injection(text: str) -> bool:
    """Return True if ``text`` contains potential prompt injection patterns."""
    return any(pattern.search(text) for pattern in _compiled)
