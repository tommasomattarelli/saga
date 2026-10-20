"""Real PostgreSQL round-trips for #56: a Google tool-loop turn preserves its protocol data.

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


async def _run_turn(
    auth_client, responses: list[genai_types.GenerateContentResponse]
) -> list[dict]:
    campaign_id = await _configure_google(auth_client)
    calls: list[dict] = []

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
    return tool_calls


def _parts(contents: list[dict], kind: str) -> list[dict]:
    return [part for content in contents for part in content["parts"] if kind in part]


@pytest.mark.asyncio
async def test_real_turn_echoes_signature_for_idless_parallel_calls(auth_client) -> None:
    tool_calls = await _run_turn(
        auth_client,
        [
            _response(
                [
                    _text_part("You look around."),
                    _fc_part("request_dice", {"stat": "DEX"}, None, _SIG),
                    _fc_part("request_dice", {"stat": "STR"}, None),
                ]
            ),
            _response([_text_part("The dice settle.")]),
        ],
    )

    contents = tool_calls[1]["contents"]
    fc_parts = _parts(contents, "function_call")
    assert len(fc_parts) == 2
    assert fc_parts[0]["thought_signature"] == _SIG
    assert "thought_signature" not in fc_parts[1]
    # No native id existed, so the internal one must not leak into the payload.
    assert all("id" not in part["function_call"] for part in fc_parts)


@pytest.mark.asyncio
async def test_real_turn_echoes_native_ids_on_calls_and_results(auth_client) -> None:
    tool_calls = await _run_turn(
        auth_client,
        [
            _response(
                [
                    _text_part("You look around."),
                    _fc_part("request_dice", {"stat": "DEX"}, "native-dex"),
                    _fc_part("request_dice", {"stat": "STR"}, "native-str"),
                ]
            ),
            _response([_text_part("The dice settle.")]),
        ],
    )

    contents = tool_calls[1]["contents"]
    call_ids = [part["function_call"]["id"] for part in _parts(contents, "function_call")]
    response_ids = [
        part["function_response"]["id"] for part in _parts(contents, "function_response")
    ]
    assert call_ids == ["native-dex", "native-str"]
    assert response_ids == call_ids
