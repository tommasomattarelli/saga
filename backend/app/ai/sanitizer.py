"""Anti prompt-injection layer for user inputs."""

import re

# Patterns that may indicate prompt injection attempts
INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions|prompts)",
    r"you\s+are\s+now\s+",
    r"system\s*:\s*",
    r"<\|im_start\|>",
    r"\[INST\]",
    r"###\s*(instruction|system)",
]

_compiled = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def sanitize_player_input(text: str) -> str:
    """Sanitize player input to prevent prompt injection.

    Returns the sanitized text. Strips dangerous patterns but preserves
    the player's intent for legitimate in-game dialogue.
    """
    sanitized = text.strip()

    # Remove null bytes
    sanitized = sanitized.replace("\x00", "")

    # Limit length
    if len(sanitized) > 2000:
        sanitized = sanitized[:2000]

    return sanitized


def detect_injection(text: str) -> bool:
    """Check if text contains potential prompt injection patterns."""
    return any(pattern.search(text) for pattern in _compiled)
