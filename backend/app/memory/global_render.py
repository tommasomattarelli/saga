from html import escape

from app.memory.document_contracts import GlobalPayload


def render_global_sections(payload: GlobalPayload) -> str:
    sections = [f"<story_so_far>{escape(payload.story_so_far)}</story_so_far>"]
    for name, values in (
        ("open_threads", payload.open_threads),
        ("relationships", payload.relationships),
        ("resolved_threads", payload.resolved_threads),
    ):
        entries = "".join(f"<item>{escape(text)}</item>" for text in values)
        sections.append(f"<{name}>{entries}</{name}>")
    return "\n".join(sections)
