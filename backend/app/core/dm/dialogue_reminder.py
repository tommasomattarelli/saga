import json
from xml.sax.saxutils import escape

from app.ai.prompts.loader import template
from app.core.campaign_language import LANGUAGES, validate_language
from app.core.dm.dialogue_composition import NPCLine, placement_events
from app.core.dm.npc_context import NPCBeat


def dialogue_reminder(
    registry: list[NPCLine],
    beats: list[NPCBeat],
    segments: list[dict],
    language: str,
    closing: bool,
) -> str:
    placed = {event.line.handle for event in placement_events(segments, registry) if event.line}
    public = {
        "completed_beats": [
            {"step": beat.step, "actors": [r.npc_name for r in beat.results]} for beat in beats
        ],
        "available_handles": [line.handle for line in registry],
        "unplaced_handles": [line.handle for line in registry if line.handle not in placed],
    }
    return template("dm", "dialogue_reminder").format(
        campaign_language=f"{LANGUAGES[validate_language(language)]} ({language})",
        public_state=escape(json.dumps(public, ensure_ascii=False)),
        next_step=template("dm", "dialogue_closing" if closing else "dialogue_open"),
    )
