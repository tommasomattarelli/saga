from __future__ import annotations

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


def strip_code_fences(raw: str) -> str:
    """Strip a leading/trailing markdown code fence from LLM output."""
    match = _FENCE_RE.search(raw)
    return match.group(1).strip() if match else raw.strip()


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
