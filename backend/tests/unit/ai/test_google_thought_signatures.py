"""Acceptance tests for #56 — Gemini thought_signature survives the DM tool loop.

The signature is opaque data on a function-call Part (bytes). It must travel
Google response -> internal AgentResponse -> LangChain messages -> raw dicts ->
the next Google request verbatim, without ever reaching OpenAI-compatible payloads.
"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types as genai_types

from app.ai.context import GameContext
from app.ai.providers.google import GoogleProvider
from app.ai.router import ModelConfig
from app.core.dm.dm_graph import dm_graph

_SIG_1 = b"\x00\x01opaque-signature-one"
_SIG_2 = b"\xfe\xffopaque-signature-two"


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


def _make_google_provider(monkeypatch, responses):
    calls: list[dict] = []

    class _Models:
        async def generate_content(self, **kwargs):
            calls.append(kwargs)
            return responses[len(calls) - 1]

    client = MagicMock()
    client.aio.models = _Models()
    monkeypatch.setattr("app.ai.providers.google.genai.Client", lambda **_: client)
    return GoogleProvider(api_key="test-key"), calls


def _initial_state() -> dict:
    return {
        "player_action": "I look around",
        "campaign_id": "cid",
        "user_id": "uid",
        "messages": [],
        "world_state": {"npcs": {}},
        "char_data": {},
        "world_baseline": {},
        "difficulty": "medium",
        "narration": "",
        "narration_segments": [],
        "scene_mood": "neutral",
        "tool_events": [],
        "dice_results": [],
        "npc_dialogues": [],
        "called_npcs": [],
        "time_passed_minutes": 0,
        "model_used": "",
        "importance_score": 0,
        "step_count": 1,
        "consecutive_empty_steps": 0,
        "death_event": None,
        "system_prompt": "",
        "model_config": {},
    }


@contextmanager
def _graph_env(provider):
    campaign = MagicMock()
    campaign.world_state = {}
    campaign.character_data = {}
    campaign.quests = {}
    campaign.world_baseline = {}
    campaign.difficulty = "medium"

    db_result = MagicMock()
    db_result.scalar_one.return_value = campaign
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=db_result)

    @asynccontextmanager
    async def fake_ctx():
        yield mock_db

    game_ctx = GameContext(messages=[], importance_score=1, system_prompt="sys")
    model_cfg = ModelConfig(provider="google", model="gemini-3.5-flash", max_tokens=1000)

    with (
        patch(
            "app.core.dm.dm_nodes.get_user_generation",
            new=AsyncMock(return_value=(provider, model_cfg)),
        ),
        patch("app.memory.recall.snapshot_recall_query", new=AsyncMock(return_value=None)),
        patch("app.dependencies.get_db_context", side_effect=fake_ctx),
        patch("app.core.dm.dm_nodes.build_context", new=AsyncMock(return_value=game_ctx)),
        patch("app.core.dm.dm_nodes.sanitize_player_input", side_effect=lambda x: x),
        patch("app.core.dm.dm_nodes.detect_injection", return_value=False),
    ):
        yield


def _fc_parts(contents: list[dict]) -> list[dict]:
    return [part for content in contents for part in content["parts"] if "function_call" in part]


def _model_text_parts(contents: list[dict]) -> list[dict]:
    return [
        part
        for content in contents
        if content["role"] == "model"
        for part in content["parts"]
        if "text" in part
    ]


def _fr_parts(contents: list[dict]) -> list[dict]:
    return [
        part for content in contents for part in content["parts"] if "function_response" in part
    ]


class TestSingleToolCall:
    @pytest.mark.asyncio
    async def test_next_request_echoes_signature(self, monkeypatch):
        provider, calls = _make_google_provider(
            monkeypatch,
            [
                _response(
                    [
                        _text_part("You roll."),
                        _fc_part("request_dice", {"stat": "DEX"}, "call-1", _SIG_1),
                    ]
                ),
                _response([_text_part("The die lands.")]),
            ],
        )

        with _graph_env(provider):
            await dm_graph.ainvoke(_initial_state(), config={})

        assert len(calls) == 2
        rebuilt = _fc_parts(calls[1]["contents"])
        assert len(rebuilt) == 1
        assert rebuilt[0]["thought_signature"] == _SIG_1
        # The payload must be valid for the installed SDK (bytes survive validation).
        assert genai_types.Part.model_validate(rebuilt[0]).thought_signature == _SIG_1


class TestSequentialSteps:
    @pytest.mark.asyncio
    async def test_each_step_keeps_its_own_signature(self, monkeypatch):
        provider, calls = _make_google_provider(
            monkeypatch,
            [
                _response(
                    [
                        _text_part("step one"),
                        _fc_part("request_dice", {"stat": "DEX"}, "c1", _SIG_1),
                    ]
                ),
                _response(
                    [
                        _text_part("step two"),
                        _fc_part("request_dice", {"stat": "STR"}, "c2", _SIG_2),
                    ]
                ),
                _response([_text_part("done")]),
            ],
        )

        with _graph_env(provider):
            await dm_graph.ainvoke(_initial_state(), config={})

        assert len(calls) == 3
        signatures = [p.get("thought_signature") for p in _fc_parts(calls[2]["contents"])]
        assert signatures == [_SIG_1, _SIG_2]


class TestParallelToolCalls:
    @pytest.mark.asyncio
    async def test_signature_stays_on_first_call_only(self, monkeypatch):
        provider, calls = _make_google_provider(
            monkeypatch,
            [
                _response(
                    [
                        _fc_part("request_dice", {"stat": "DEX"}, "c1", _SIG_1),
                        _fc_part("request_dice", {"stat": "STR"}, "c2"),
                    ]
                ),
                _response([_text_part("both resolved")]),
            ],
        )

        with _graph_env(provider):
            await dm_graph.ainvoke(_initial_state(), config={})

        rebuilt = _fc_parts(calls[1]["contents"])
        assert len(rebuilt) == 2
        assert rebuilt[0]["thought_signature"] == _SIG_1
        assert "thought_signature" not in rebuilt[1]
        # Both function responses are still delivered, associated by order.
        responses = [
            part["function_response"]["name"]
            for content in calls[1]["contents"]
            for part in content["parts"]
            if "function_response" in part
        ]
        assert responses == ["request_dice", "request_dice"]

    @pytest.mark.asyncio
    async def test_idless_parallel_calls_keep_signatures_separate(self, monkeypatch):
        # Google may omit call ids; two same-named calls must not collapse onto one key
        # (the regression where both parts came back carrying the first call's signature).
        provider, calls = _make_google_provider(
            monkeypatch,
            [
                _response(
                    [
                        _fc_part("request_dice", {"stat": "DEX"}, None, _SIG_1),
                        _fc_part("request_dice", {"stat": "STR"}, None),
                    ]
                ),
                _response([_text_part("both resolved")]),
            ],
        )

        with _graph_env(provider):
            await dm_graph.ainvoke(_initial_state(), config={})

        rebuilt = _fc_parts(calls[1]["contents"])
        assert len(rebuilt) == 2
        assert rebuilt[0]["thought_signature"] == _SIG_1
        assert "thought_signature" not in rebuilt[1]
        # Internal synthetic ids stay out of the payload Google sees.
        assert "id" not in rebuilt[0]["function_call"]
        assert "id" not in rebuilt[1]["function_call"]
        assert all("id" not in p["function_response"] for p in _fr_parts(calls[1]["contents"]))

    @pytest.mark.asyncio
    async def test_native_ids_are_echoed_on_calls_and_results(self, monkeypatch):
        # Gemini 3 returns a unique id per call; the functionResponse must carry it back.
        provider, calls = _make_google_provider(
            monkeypatch,
            [
                _response(
                    [
                        _fc_part("request_dice", {"stat": "DEX"}, "native-dex", _SIG_1),
                        _fc_part("request_dice", {"stat": "STR"}, "native-str"),
                    ]
                ),
                _response([_text_part("both resolved")]),
            ],
        )

        with _graph_env(provider):
            await dm_graph.ainvoke(_initial_state(), config={})

        contents = calls[1]["contents"]
        call_ids = [p["function_call"]["id"] for p in _fc_parts(contents)]
        response_ids = [p["function_response"]["id"] for p in _fr_parts(contents)]
        assert call_ids == ["native-dex", "native-str"]
        assert response_ids == call_ids


class TestTextPartSignature:
    @pytest.mark.asyncio
    async def test_text_signature_is_echoed(self, monkeypatch):
        # Gemini 2.5 may put the signature on the first part whatever its type.
        provider, calls = _make_google_provider(
            monkeypatch,
            [
                _response(
                    [
                        _text_part("A low growl.", _SIG_1),
                        _fc_part("request_dice", {"stat": "DEX"}),
                    ]
                ),
                _response([_text_part("resolved")]),
            ],
        )

        with _graph_env(provider):
            await dm_graph.ainvoke(_initial_state(), config={})

        text_parts = _model_text_parts(calls[1]["contents"])
        assert text_parts
        assert text_parts[0]["thought_signature"] == _SIG_1


class TestUnsignedResponse:
    @pytest.mark.asyncio
    async def test_unsigned_call_still_works(self, monkeypatch):
        provider, calls = _make_google_provider(
            monkeypatch,
            [
                _response([_fc_part("request_dice", {"stat": "DEX"}, "c1")]),
                _response([_text_part("resolved")]),
            ],
        )

        with _graph_env(provider):
            await dm_graph.ainvoke(_initial_state(), config={})

        rebuilt = _fc_parts(calls[1]["contents"])
        assert len(rebuilt) == 1
        assert "thought_signature" not in rebuilt[0]


class TestOtherProvidersUnaffected:
    def _assistant_with_metadata(self) -> dict:
        return {
            "role": "assistant",
            "content": "I look around.",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "request_dice", "arguments": "{}"},
                }
            ],
            "tool_call_signatures": {"c1": _SIG_1},
            "text_thought_signature": _SIG_2,
        }

    @pytest.mark.asyncio
    async def test_openai_payload_has_no_google_metadata(self, monkeypatch):
        from app.ai.providers.openai import OpenAIProvider

        client = MagicMock()
        monkeypatch.setattr("app.ai.providers.openai.openai.AsyncOpenAI", lambda **_: client)
        provider = OpenAIProvider(api_key="sk-test")

        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message.content = "ok"
        choice.message.tool_calls = None
        response = MagicMock()
        response.choices = [choice]
        create = AsyncMock(return_value=response)
        provider.client.chat.completions.create = create

        await provider.generate_with_tools("sys", [self._assistant_with_metadata()], tools=[])

        sent = create.call_args.kwargs["messages"]
        assert all("tool_call_signatures" not in m for m in sent)
        assert all("text_thought_signature" not in m for m in sent)

    @pytest.mark.asyncio
    async def test_local_payload_has_no_google_metadata(self, monkeypatch):
        from app.ai.providers.local import LocalProvider

        client = MagicMock()
        monkeypatch.setattr("app.ai.providers.local.openai.AsyncOpenAI", lambda **_: client)
        provider = LocalProvider(base_url="http://localhost:8080/v1", api_key="local")

        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message.content = "ok"
        choice.message.tool_calls = None
        response = MagicMock()
        response.choices = [choice]
        create = AsyncMock(return_value=response)
        provider.client.chat.completions.create = create

        await provider.generate_with_tools("sys", [self._assistant_with_metadata()], tools=[])

        sent = create.call_args.kwargs["messages"]
        assert all("tool_call_signatures" not in m for m in sent)
        assert all("text_thought_signature" not in m for m in sent)
