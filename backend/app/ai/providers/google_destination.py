"""The Google SDK destination shared by settings and the provider."""

from __future__ import annotations

import os
from dataclasses import dataclass

from google.genai._base_url import get_base_url
from google.genai.types import HttpOptions

# These are google-genai 1.68.0's explicit-key defaults for each API mode.
_VERTEX_DEFAULT_URL = "https://aiplatform.googleapis.com/"
_GEMINI_DEFAULT_URL = "https://generativelanguage.googleapis.com/"


@dataclass(frozen=True)
class GoogleDestination:
    vertexai: bool
    base_url: str | None

    @property
    def mode(self) -> str:
        return "vertex" if self.vertexai else "developer"

    @property
    def effective_url(self) -> str:
        if self.base_url:
            return self.base_url
        return _VERTEX_DEFAULT_URL if self.vertexai else _GEMINI_DEFAULT_URL

    def http_options(self) -> HttpOptions | None:
        if not self.base_url:
            return None
        return HttpOptions(base_url=self.base_url)


def resolve_google_destination() -> GoogleDestination:
    # Client resolves this before BaseApiClient applies the Vertex environment setting.
    return GoogleDestination(
        vertexai=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "0").lower() in {"true", "1"},
        base_url=get_base_url(False),
    )
