import re
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import quote

from app.core.dialogue_markers import RESERVED_MARKER, RESERVED_START
from app.schemas.narration import NarrationPart, NarrationSegment, NPCSpeechPart, TextPart

_PLACEMENT = re.compile(r"\[\[\s*npc:([^:\[\]\n]+):([1-9]\d*)\s*\]\]", re.IGNORECASE)
_SAFE_LABEL = re.compile(r"[^:\[\]~%\n\r]+")


@dataclass(frozen=True)
class NPCLine:
    handle: str
    label: str
    beat: int
    step: int
    part: NPCSpeechPart


@dataclass(frozen=True)
class Placement:
    source_index: int
    marker: re.Match[str]
    line: NPCLine | None


def placement_events(raw: list[dict], registry: list[NPCLine]) -> Iterator[Placement]:
    available = {(line.label.casefold(), str(line.part.line_index)): line for line in registry}
    placed: set[str] = set()
    for index, source in enumerate(raw):
        for marker in RESERVED_MARKER.finditer(source.get("text", "")):
            match = _PLACEMENT.fullmatch(marker.group())
            line = available.get((match[1].strip().casefold(), match[2])) if match else None
            if line and line.step < source["step"] and line.handle not in placed:
                placed.add(line.handle)
            else:
                line = None
            yield Placement(index, marker, line)


def _inside_quote(text: str) -> bool:
    pairs = {'"': '"', "“": "”", "«": "»"}
    closing = ""
    escaped = False
    for char in text:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif closing:
            if char == closing:
                closing = ""
        elif char in pairs:
            closing = pairs[char]
    return bool(closing)


def clean_narration(
    text: str, step: int, previous: list[dict], registry: list[NPCLine]
) -> tuple[str, int]:
    cuts: list[tuple[int, int]] = []
    pairs = {'"': '"', "“": "”", "«": "»"}
    for event in placement_events([*previous, {"step": step, "text": text}], registry):
        if event.source_index != len(previous) or event.line is None:
            continue
        start = event.marker.end()
        prefix = text[: event.marker.start()]
        if prefix.strip() and not prefix.rstrip().endswith((".", "!", "?")):
            continue
        suffix = text[start:]
        candidate = suffix.lstrip()
        if (
            not candidate
            or candidate[0] not in pairs
            or _inside_quote(text[: event.marker.start()])
        ):
            continue
        quote = candidate[0] + event.line.part.dialogue + pairs[candidate[0]]
        if not candidate.startswith(quote):
            continue
        end = start + len(suffix) - len(candidate) + len(quote)
        tail = text[end:]
        # An inline attribution or orphaned punctuation makes the speaker ambiguous.
        if (
            tail.strip()
            and not re.match(r"[ \t]*\r?\n[ \t]*\r?\n", tail)
            and not _PLACEMENT.match(tail.lstrip())
        ):
            continue
        cuts.append((start, end))
    for start, end in reversed(cuts):
        text = text[:start] + text[end:]
    return text, len(cuts)


def public_name(name: str) -> str:
    return RESERVED_START.sub(lambda m: m.group().replace("[[", "［［"), name)


def register_lines(
    registry: list[NPCLine],
    npc_id: str,
    name: str,
    lines: tuple[str, ...],
    *,
    step: int,
    beat: int,
    ambiguous_names: set[str] | None = None,
) -> list[NPCLine]:
    existing = [line for line in registry if line.part.npc_id == npc_id]
    label = existing[0].label if existing else name
    if not existing and (
        not _SAFE_LABEL.fullmatch(name)
        or name != name.strip()
        or name.casefold() in (ambiguous_names or set())
        or any(line.label.casefold() == name.casefold() for line in registry)
    ):
        label = quote(name, safe="").replace("~", "%7E") + "~" + quote(npc_id, safe="")
    created = []
    for index, text in enumerate(lines, start=len(existing) + 1):
        created.append(
            NPCLine(
                handle=f"[[npc:{label}:{index}]]",
                label=label,
                beat=beat,
                step=step,
                part=NPCSpeechPart(
                    npc_id=npc_id, npc_name=public_name(name), line_index=index, dialogue=text
                ),
            )
        )
    registry.extend(created)
    return created


def compose_segments(raw: list[dict], registry: list[NPCLine]) -> list[NarrationSegment]:
    prepared: list[dict] = []
    for source in raw:
        text, _ = clean_narration(source.get("text", ""), source["step"], prepared, registry)
        prepared.append({**source, "text": text})
    events: dict[int, list[Placement]] = {}
    for event in placement_events(prepared, registry):
        events.setdefault(event.source_index, []).append(event)
    placed: set[str] = set()
    segments = []
    for index, source in enumerate(prepared):
        parts: list[NarrationPart] = []
        text = source.get("text", "")
        cursor = 0
        for event in events.get(index, []):
            marker, line = event.marker, event.line
            if marker.start() > cursor:
                parts.append(TextPart(text=text[cursor : marker.start()]))
            if line:
                parts.append(line.part)
                placed.add(line.handle)
            cursor = marker.end()
        if text[cursor:]:
            parts.append(TextPart(text=text[cursor:]))
        if parts or source.get("dice"):
            segments.append(
                NarrationSegment(step=source["step"], dice=source.get("dice"), parts=parts)
            )
    unplaced = [line.part for line in registry if line.handle not in placed]
    if unplaced:
        segments.append(
            NarrationSegment(
                step=max((source["step"] for source in raw), default=-1) + 1,
                parts=list(unplaced),
            )
        )
    return segments


def transcript(segments: list[NarrationSegment]) -> str:
    return "\n".join(
        part.text if isinstance(part, TextPart) else f'{part.npc_name}: "{part.dialogue}"'
        for segment in segments
        for part in segment.parts
        if not isinstance(part, TextPart) or part.text.strip()
    )
