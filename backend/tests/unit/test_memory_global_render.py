from xml.etree import ElementTree

from app.memory.document_contracts import GlobalPayload
from app.memory.global_render import render_global_sections


def test_global_sections_preserve_order_escape_text_and_keep_empty_sections() -> None:
    payload = GlobalPayload(
        story_so_far='Mira saw <the gate> & said "wait".',
        open_threads=("A second debt", "A first promise"),
        relationships=(),
        resolved_threads=("The <key> was returned.",),
    )
    content = render_global_sections(payload)
    root = ElementTree.fromstring(f"<global_summary>{content}</global_summary>")
    assert [child.tag for child in root] == [
        "story_so_far",
        "open_threads",
        "relationships",
        "resolved_threads",
    ]
    assert root.findtext("story_so_far") == payload.story_so_far
    assert [item.text for item in root.findall("open_threads/item")] == list(payload.open_threads)
    assert root.find("relationships") is not None
    assert root.findtext("resolved_threads/item") == payload.resolved_threads[0]
    assert render_global_sections(payload) == content
