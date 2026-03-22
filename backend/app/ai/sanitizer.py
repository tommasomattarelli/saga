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


TEMPLATE_CONTENT_START = "<<COMMUNITY_TEMPLATE_CONTENT_BEGIN>>"
TEMPLATE_CONTENT_END = "<<COMMUNITY_TEMPLATE_CONTENT_END>>"


def sanitize_player_input(text: str) -> str:
    """Sanitize player input to prevent injection (max 2000 chars)."""
    sanitized = text.strip()
    sanitized = sanitized.replace("\x00", "")
    if len(sanitized) > 2000:
        sanitized = sanitized[:2000]
    return sanitized


def sanitize_template_field(text: str) -> str:
    """Sanitize community template field to remove injection patterns."""
    sanitized = text.strip().replace("\x00", "")
    for pattern in _compiled:
        sanitized = pattern.sub("[REMOVED]", sanitized)
    if len(sanitized) > 4000:
        sanitized = sanitized[:4000]
    return sanitized


def wrap_template_content(text: str) -> str:
    """Wrap sanitized template text in delimiters for semantic isolation."""
    return f"{TEMPLATE_CONTENT_START}\n{text}\n{TEMPLATE_CONTENT_END}"


def detect_injection(text: str) -> bool:
    """Return True if ``text`` contains potential prompt injection patterns."""
    return any(pattern.search(text) for pattern in _compiled)
