"""Probes: the obligations under test, and the grader that scores them.

A probe owns the *check* — "did it call invoke_npc", "did it restate the NPC's
line" — and nothing else. The *stimulus* (what the player types, which NPC line
gets injected) comes from the scenario, because you cannot ask a model to pick up
a knife at the foot of a menhir in a scene that has no menhir. The check travels;
the prose does not.

That split is what makes the delta measurable: the same probe runs against an
empty context and a saturated one, and only the surrounding prompt differs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Probe:
    name: str
    why: str
    must_call: frozenset[str] = frozenset()
    must_not_call: frozenset[str] = frozenset()
    forbid_quoted_dialogue: bool = False
    #: needs a prior invoke_npc tool result injected into the history
    needs_injected_npc: bool = False
    #: re-label a missed obligation as silent desync when the turn was narrated anyway
    flag_silent_narration: bool = False


PROBES: list[Probe] = [
    Probe(
        name="npc_speaks",
        why="dm.yaml:31 — a present NPC answering MUST go through invoke_npc (#52)",
        must_call=frozenset({"invoke_npc"}),
    ),
    Probe(
        name="npc_followup",
        why="dm.yaml:42 — after an invoke_npc result, do not restate the line (#53)",
        must_not_call=frozenset({"invoke_npc"}),
        forbid_quoted_dialogue=True,
        needs_injected_npc=True,
    ),
    Probe(
        name="item_pickup",
        why="dm.yaml:30 — acquiring an object MUST call add_item",
        must_call=frozenset({"add_item"}),
    ),
    Probe(
        name="passive_turn",
        why="dm.yaml:20/35 — a passive turn still advances the clock",
        must_call=frozenset({"advance_time"}),
    ),
    Probe(
        name="narration_without_tool",
        why="dm.yaml:37 BACKSTOP — a narrated state change with no tool call desyncs the world",
        must_call=frozenset({"remove_item"}),
        flag_silent_narration=True,
    ),
]

PROBES_BY_NAME = {p.name: p for p in PROBES}


@dataclass
class Stimulus:
    """What the scenario hands a probe: the turn's input, in that scene's terms."""

    player: str
    npc_name: str = ""
    npc_dialogue: str = ""
    npc_action: str = ""
    npc_context: str = ""
    tool_calls: list[dict] = field(default_factory=list)


# --- language ---------------------------------------------------------------
# A stopword count, not a detector. Enough to catch a whole turn coming back in
# the wrong language, which is the failure #51 describes; it would not survive a
# single mixed sentence, and is not asked to.

_WORDS = {
    "it": {
        "che",
        "non",
        "di",
        "il",
        "la",
        "un",
        "una",
        "sono",
        "per",
        "con",
        "del",
        "nel",
        "ti",
        "si",
        "e'",
        "sul",
        "come",
        "tuo",
        "tua",
        "quando",
    },
    "en": {
        "the",
        "you",
        "and",
        "of",
        "to",
        "is",
        "your",
        "with",
        "from",
        "that",
        "into",
        "his",
        "her",
        "they",
        "for",
        "at",
        "on",
        "as",
        "it",
        "are",
    },
}


def language(text: str) -> str:
    words = re.findall(r"[a-zà-ù']+", text.lower())
    counts = {code: sum(w in vocab for w in words) for code, vocab in _WORDS.items()}
    best = max(counts, key=lambda code: counts[code])
    ties = [code for code, n in counts.items() if n == counts[best]]
    return "?" if len(ties) > 1 else best


# --- narration checks -------------------------------------------------------

_MARKDOWN = re.compile(r"\*\*|^#{1,6}\s|^\s*[-*]\s", re.MULTILINE)
_MECHANICS = re.compile(
    r"\bDC\s*\d|\bd20\b|\b(?:Mood|Time|Roll|Suggested actions|Tool Call)\s*:", re.IGNORECASE
)
_QUOTED = re.compile(r"[«\"“][^»\"”]{12,}[»\"”]")

#: Above this, the DM wrote a real turn rather than deflecting the action.
SILENT_NARRATION_CHARS = 200


def grade(probe: Probe, text: str, called: set[str], expect_language: str = "it") -> list[str]:
    """Returns the failed check names — empty means a clean pass.

    `expect_language` comes from the scenario: gold is authored in English, the
    built-in empty scenario is Italian, and flagging either as wrong would be the
    grader lying about the thing it exists to measure.
    """
    failed = []
    if missing := probe.must_call - called:
        # Two very different failures wear the same missing tool call. Declining the
        # action is merely unhelpful; narrating a full turn as though it happened and
        # recording nothing is a world state that disagrees with what the player read,
        # and nothing downstream can see the disagreement. Length is the proxy for
        # "the DM committed to it" — crude, but it separates the safe miss from the
        # dangerous one, and the dangerous one is the whole reason this probe exists.
        if probe.flag_silent_narration and len(text.strip()) > SILENT_NARRATION_CHARS:
            failed.append(f"narrated-not-called:{','.join(sorted(missing))}")
        else:
            failed.append(f"missing:{','.join(sorted(missing))}")
    if forbidden := probe.must_not_call & called:
        failed.append(f"forbidden:{','.join(sorted(forbidden))}")

    if text.strip():
        detected = language(text)
        if detected != "?" and detected != expect_language:
            failed.append(f"language:{detected}")

    if _MARKDOWN.search(text):
        failed.append("markdown")
    if _MECHANICS.search(text):
        failed.append("mechanics-leak")
    # Proxy, not proof: a long quoted span after an NPC result is a restatement.
    if probe.forbid_quoted_dialogue and _QUOTED.search(text):
        failed.append("restates-npc")
    return failed
