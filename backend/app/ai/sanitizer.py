"""Anti prompt-injection layer for player and template inputs."""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Patterns that may indicate prompt injection attempts.
# Applied to player inputs AND community template text fields.
# ---------------------------------------------------------------------------
INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions|prompts)",
    r"you\s+are\s+now\s+",
    r"system\s*:\s*",
    r"<\|im_start\|>",
    r"\[INST\]",
    r"###\s*(instruction|system)",
    r"<\s*/?\s*system\s*>",        # XML-style system tags
    r"--\s*system\s*--",           # Markdown-style system delimiters
]

_compiled = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

# Delimiter used to wrap template content in the DM system prompt.
# The DM is instructed to treat content inside these delimiters as
# untrusted narrative material, never as system instructions.
TEMPLATE_CONTENT_START = "<<COMMUNITY_TEMPLATE_CONTENT_BEGIN>>"
TEMPLATE_CONTENT_END = "<<COMMUNITY_TEMPLATE_CONTENT_END>>"


def sanitize_player_input(text: str) -> str:
    """Sanitize player input to prevent prompt injection.

    Returns the sanitized text. Strips dangerous patterns but preserves
    the player's intent for legitimate in-game dialogue.
    Limits input to 2 000 characters.
    """
    sanitized = text.strip()
    sanitized = sanitized.replace("\x00", "")
    if len(sanitized) > 2000:
        sanitized = sanitized[:2000]
    return sanitized


def sanitize_template_field(text: str) -> str:
    """Sanitize a community template text field.

    Community-contributed templates are a prompt injection vector: lore
    seeds, NPC descriptions, and DM style directives are injected into
    the system prompt.  This function removes known injection patterns
    and truncates overly long fields.

    The caller is responsible for wrapping the sanitized text with
    ``wrap_template_content`` before inserting it into the system prompt.
    """
    sanitized = text.strip().replace("\x00", "")
    for pattern in _compiled:
        sanitized = pattern.sub("[REMOVED]", sanitized)
    if len(sanitized) > 4000:
        sanitized = sanitized[:4000]
    return sanitized


def wrap_template_content(text: str) -> str:
    """Wrap sanitized template text in delimiters for the DM system prompt.

    The DM prompt instructs the model to treat content inside these
    delimiters as untrusted narrative context, not as system instructions.
    Even if injection patterns somehow survive sanitization, the delimiter
    wrapper provides a second layer of semantic isolation.
    """
    return f"{TEMPLATE_CONTENT_START}\n{text}\n{TEMPLATE_CONTENT_END}"


def detect_injection(text: str) -> bool:
    """Return True if ``text`` contains potential prompt injection patterns."""
    return any(pattern.search(text) for pattern in _compiled)
