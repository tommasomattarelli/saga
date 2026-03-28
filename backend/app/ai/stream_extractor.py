"""Extract narration text from a streaming JSON response.

The DM returns JSON with `narration` as the first field. This state machine
extracts only the narration text from the token stream, filtering out JSON
syntax so the frontend receives clean prose.

For non-JSON responses (e.g. dice re-prompt plain text), all text is passed through.
"""

from enum import Enum, auto


class _State(Enum):
    DETECTING = auto()
    IN_NARRATION = auto()
    DONE = auto()


class NarrationExtractor:
    def __init__(self) -> None:
        self._buffer = ""
        self._state = _State.DETECTING
        self._escape_next = False
        self._is_json = False
        self._narration_started = False

    def feed(self, chunk: str) -> str:
        if self._state == _State.DONE:
            return ""

        self._buffer += chunk

        if self._state == _State.DETECTING:
            return self._detect()

        if self._state == _State.IN_NARRATION:
            return self._extract_narration(chunk)

        return ""

    def _detect(self) -> str:
        stripped = self._buffer.lstrip()
        if not stripped:
            return ""

        if stripped[0] == "{":
            self._is_json = True
            marker = '"narration"'
            idx = stripped.find(marker)
            if idx == -1:
                if len(stripped) > 200:
                    self._state = _State.DONE
                return ""
            after_key = stripped[idx + len(marker) :]
            colon_pos = after_key.find(":")
            if colon_pos == -1:
                return ""
            after_colon = after_key[colon_pos + 1 :].lstrip()
            if not after_colon:
                return ""
            if after_colon[0] == '"':
                self._state = _State.IN_NARRATION
                self._narration_started = True
                remaining = after_colon[1:]
                self._buffer = ""
                return self._extract_narration(remaining)
            return ""
        else:
            self._state = _State.IN_NARRATION
            self._is_json = False
            text = self._buffer
            self._buffer = ""
            return text

    def _extract_narration(self, text: str) -> str:
        if not self._is_json:
            return text

        out = []
        for ch in text:
            if self._escape_next:
                if ch == "n":
                    out.append("\n")
                elif ch == "t":
                    out.append("\t")
                elif ch == '"':
                    out.append('"')
                elif ch == "\\":
                    out.append("\\")
                else:
                    out.append(ch)
                self._escape_next = False
                continue

            if ch == "\\":
                self._escape_next = True
                continue

            if ch == '"':
                self._state = _State.DONE
                return "".join(out)

            out.append(ch)

        return "".join(out)
