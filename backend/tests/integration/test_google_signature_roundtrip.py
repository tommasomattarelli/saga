"""Real PostgreSQL round-trip for #56: a Google tool-loop turn echoes the signature.

Runs the real DM graph and real credential resolution against the test database, with
only the Google SDK transport faked, and inspects the contents actually delivered to
the second generate_content call of the same turn.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types as genai_types

from app.ai.providers import base

_SIG = b"\x00\xffintegration-signature"


def _text_part(text: str, signature: bytes | None = None) -> genai_types.Part:
    return genai_types.Part(text=text, thought_signature=signature)


def _fc_part(
    name: str, args: dict, call_id: str | None = None, signature: bytes | None = None
) -> genai_types.Part:
    return genai_types.Part(
        function_call=genai_types.FunctionCall(name=name, args=args, id=call_id),
        thought_signature=signature,
    )


def _response(parts: list[genai_types.Part]) -> genai_types.GenerateContentResponse:
    return genai_types.GenerateContentResponse(
        candidates=[genai_types.Candidate(content=genai_types.Content(role="model", parts=parts))]
    )


async def _configure_google(client) -> str:
    resp = await client.put("/api/settings/api-keys", json={"google": "test-google-key"})
    assert resp.status_code == 200
    resp = await client.patch(
        "/api/settings",
        json={"generation_provider": "google", "generation_model": "gemini-3.5-flash"},
    )
    assert resp.status_code == 200
    resp = await client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": "Signature Roundtrip", "difficulty": "medium"},
    )
    assert resp.status_code == 201
    return str(resp.json()["id"])


@pytest.mark.asyncio
async def test_real_turn_echoes_signature_to_the_next_google_request(auth_client) -> None:
    campaign_id = await _configure_google(auth_client)

    calls: list[dict] = []
    responses = [
        _response(
            [
                _text_part("You look around."),
                _fc_part("request_dice", {"stat": "DEX"}, None, _SIG),
                _fc_part("request_dice", {"stat": "STR"}, None),
            ]
        ),
        _response([_text_part("The dice settle.")]),
    ]

    class _Models:
        async def generate_content(self, **kwargs):
            calls.append(kwargs)
            return responses[len(calls) - 1]

    client = MagicMock()
    client.aio.models = _Models()

    base._providers.clear()
    try:
        with (
            patch("app.ai.providers.google.genai.Client", lambda **_: client),
            patch(
                "app.ai.embeddings.generate_embedding",
                new=AsyncMock(return_value=[0.0] * 384),
            ),
            patch(
                "app.api.turns.generate_embedding",
                new=AsyncMock(return_value=[0.0] * 384),
            ),
            patch(
                "app.api.turns.compress_turn_to_summary",
                new=AsyncMock(return_value="summary"),
            ),
            patch("app.api.turns.extract_and_store_facts", new=AsyncMock(return_value=None)),
            patch("app.api.turns._background_compression", new=AsyncMock(return_value=None)),
            patch("app.api.turns._background_global_summary", new=AsyncMock(return_value=None)),
        ):
            resp = await auth_client.post(
                f"/api/campaigns/{campaign_id}/action", json={"action": "I look around"}
            )
    finally:
        base._providers.clear()

    assert resp.status_code == 200
    tool_calls = [c for c in calls if getattr(c.get("config"), "tools", None)]
    assert len(tool_calls) == 2

    fc_parts = [
        part
        for content in tool_calls[1]["contents"]
        for part in content["parts"]
        if "function_call" in part
    ]
    assert len(fc_parts) == 2
    assert fc_parts[0]["thought_signature"] == _SIG
    assert "thought_signature" not in fc_parts[1]
