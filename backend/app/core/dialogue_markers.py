import re

RESERVED_START = re.compile(r"\[\[\s*npc\b", re.IGNORECASE)
RESERVED_MARKER = re.compile(r"\[\[\s*npc\b[^\n\[]*?(?:\]\]|(?=\[|\n|$))", re.IGNORECASE)


def strip_markers(text: str) -> str:
    return RESERVED_MARKER.sub("", text)
