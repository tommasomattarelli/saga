"""Reasoning models put their deliberation where the answer should be. The
summarisers validate nothing, so whatever comes back is stored and re-injected
into every later prompt — these are the two things that stop that (#78)."""

import pytest

from app.ai.sanitizer import parse_json_payload, strip_reasoning


class TestStripReasoning:
    def test_removes_a_closed_think_block(self):
        raw = "<think>Let me analyse the turns.</think>\nKael reached the mine mouth."
        assert strip_reasoning(raw) == "Kael reached the mine mouth."

    def test_removes_several_blocks(self):
        raw = "<think>a</think>One.<think>b</think>Two."
        assert strip_reasoning(raw) == "One.Two."

    def test_is_case_insensitive_and_spans_newlines(self):
        assert strip_reasoning("<THINK>\nmulti\nline\n</Think>ok") == "ok"

    def test_drops_everything_after_an_unclosed_block(self):
        """A truncated reasoning model never emits the closing tag; what follows is
        deliberation, not an answer."""
        assert strip_reasoning("Prefix. <think>Let me work through") == "Prefix."

    def test_leaves_ordinary_prose_untouched(self):
        prose = "The hall is empty. Lyra holds at the bend."
        assert strip_reasoning(prose) == prose


class TestParseJsonPayload:
    def test_reads_a_bare_object(self):
        assert parse_json_payload('{"summary": "Kael woke."}') == {"summary": "Kael woke."}

    def test_reads_through_a_code_fence(self):
        assert parse_json_payload('```json\n{"summary": "ok"}\n```') == {"summary": "ok"}

    def test_repairs_mild_malformation(self):
        assert parse_json_payload('{"summary": "ok",}') == {"summary": "ok"}

    def test_finds_the_object_after_undelimited_reasoning(self):
        """Nemotron's shape: deliberation as plain prose, no tag, then the answer.
        Failing here would burn every retry on a model that did in fact answer."""
        raw = (
            "The user wants me to summarise turns 16-25. Let me analyse them.\n"
            'Turn 16: tavern.\n\n{"summary": "Kael reached the mine mouth."}'
        )
        assert parse_json_payload(raw) == {"summary": "Kael reached the mine mouth."}

    def test_ignores_braces_inside_strings(self):
        raw = 'thinking... {"summary": "he said {this} aloud"}'
        assert parse_json_payload(raw) == {"summary": "he said {this} aloud"}

    @pytest.mark.parametrize(
        "raw",
        [
            "The user wants me to extend the existing summary. Let me analyse the turns:",
            "",
            "   ",
        ],
    )
    def test_reasoning_prose_and_emptiness_are_unreadable(self, raw):
        """The whole point: deliberation must fail to parse rather than be stored."""
        assert parse_json_payload(raw) is None
