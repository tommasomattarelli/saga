"""Tests for the narration stream extractor state machine."""

from app.ai.stream_extractor import NarrationExtractor


class TestNarrationExtractor:
    def test_simple_json_narration(self):
        ext = NarrationExtractor()
        result = ext.feed('{"narration": "The dragon roars.", "scene_mood": "combat"}')
        assert result == "The dragon roars."

    def test_chunked_json(self):
        ext = NarrationExtractor()
        chunks = ['{"narr', 'ation": "Hello', " world", '.", "mood": "calm"}']
        output = ""
        for chunk in chunks:
            output += ext.feed(chunk)
        assert output == "Hello world."

    def test_escaped_quotes_in_narration(self):
        ext = NarrationExtractor()
        result = ext.feed('{"narration": "He said \\"hello\\" loudly.", "mood": "calm"}')
        assert result == 'He said "hello" loudly.'

    def test_escaped_newlines(self):
        ext = NarrationExtractor()
        result = ext.feed('{"narration": "Line one.\\nLine two.", "mood": "calm"}')
        assert result == "Line one.\nLine two."

    def test_escaped_backslash(self):
        ext = NarrationExtractor()
        result = ext.feed('{"narration": "path\\\\to\\\\file", "mood": "calm"}')
        assert result == "path\\to\\file"

    def test_non_json_passthrough(self):
        ext = NarrationExtractor()
        result = ext.feed("Just plain text response from the DM.")
        assert result == "Just plain text response from the DM."

    def test_non_json_chunked(self):
        ext = NarrationExtractor()
        out = ""
        out += ext.feed("The sword ")
        out += ext.feed("strikes true!")
        assert out == "The sword strikes true!"

    def test_whitespace_before_json(self):
        ext = NarrationExtractor()
        result = ext.feed('  \n  {"narration": "Spaced.", "mood": "neutral"}')
        assert result == "Spaced."

    def test_narration_with_colon_spacing(self):
        ext = NarrationExtractor()
        result = ext.feed('{"narration" : "With spaces.", "mood": "neutral"}')
        assert result == "With spaces."

    def test_stops_after_narration_closes(self):
        ext = NarrationExtractor()
        result = ext.feed('{"narration": "First part.')
        assert result == "First part."
        # Feed the rest — narration already closed by the quote after period+quote
        # Actually the quote hasn't appeared yet, so it's still in narration
        # Let me feed the closing quote
        result2 = ext.feed('", "scene_mood": "calm"}')
        assert result2 == ""  # Empty because closing quote ended narration

    def test_single_char_chunks(self):
        ext = NarrationExtractor()
        text = '{"narration": "Hi!", "mood": "x"}'
        out = ""
        for ch in text:
            out += ext.feed(ch)
        assert out == "Hi!"

    def test_empty_narration(self):
        ext = NarrationExtractor()
        result = ext.feed('{"narration": "", "mood": "neutral"}')
        assert result == ""

    def test_long_narration_multiline(self):
        ext = NarrationExtractor()
        narr = "The ancient door creaks open.\\nA gust of cold air rushes out.\\nYou see darkness beyond."
        result = ext.feed(f'{{"narration": "{narr}", "mood": "mystery"}}')
        expected = "The ancient door creaks open.\nA gust of cold air rushes out.\nYou see darkness beyond."
        assert result == expected

    def test_feed_after_done_returns_empty(self):
        ext = NarrationExtractor()
        ext.feed('{"narration": "Done.", "rest": true}')
        assert ext.feed("more text") == ""

    def test_markdown_fenced_json(self):
        """LLM sometimes wraps JSON in markdown fences — extractor should handle the { inside."""
        ext = NarrationExtractor()
        out = ""
        out += ext.feed("```json\n")
        out += ext.feed('{"narration": "Fenced.')
        out += ext.feed('", "mood": "x"}')
        out += ext.feed("\n```")
        assert "Fenced." in out
