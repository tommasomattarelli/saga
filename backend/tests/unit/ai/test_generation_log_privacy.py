from __future__ import annotations

import logging
import uuid
from io import StringIO
from typing import cast
from unittest.mock import patch

import pytest
import structlog
from langchain_core.messages import HumanMessage

from app.ai import npc_director
from app.ai.generation_contracts import (
    GenerationRequest,
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.npc_director import NPCInput, invoke_npcs_parallel, invoke_single_npc
from app.ai.npc_outcomes import NPCFailure, NPCSpeaking
from app.ai.providers.base import AIProvider, logged_generate
from app.ai.router import ModelConfig
from app.core.dm.dm_nodes import dm_node
from app.core.dm.game_state import GameState
from app.logging_setup import _RawJsonFormatter


class _Capture:
    def __init__(self) -> None:
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(_RawJsonFormatter())
        self.logger = logging.getLogger("llm_io")
        self.previous_level = self.logger.level
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.INFO)

    def close(self) -> str:
        try:
            self.handler.flush()
            return self.stream.getvalue()
        finally:
            self.logger.removeHandler(self.handler)
            self.logger.setLevel(self.previous_level)


class _StructlogCapture:
    def __init__(self) -> None:
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(processor=structlog.processors.JSONRenderer())
        )
        self.stdlib_logger = logging.getLogger("app.ai.npc_director")
        self.previous_level = self.stdlib_logger.level
        self.stdlib_logger.addHandler(self.handler)
        self.stdlib_logger.setLevel(logging.INFO)
        self.bound_logger = structlog.stdlib.BoundLogger(
            self.stdlib_logger,
            [
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.UnicodeDecoder(),
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            {},
        )
        self.logger_patch = patch.object(npc_director, "logger", self.bound_logger)
        self.logger_patch.start()

    def close(self) -> str:
        try:
            self.handler.flush()
            return self.stream.getvalue()
        finally:
            self.logger_patch.stop()
            self.stdlib_logger.removeHandler(self.handler)
            self.stdlib_logger.setLevel(self.previous_level)


class _Provider(AIProvider):
    failure: Exception | None = None
    response: RawGenerationReceipt | None = None
    generation_result = "raw-response-canary"

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        if self.failure is not None:
            raise self.failure
        return self.generation_result

    def stream(self, system_prompt: str, messages: list[dict], model: str, max_tokens: int = 2000):
        raise NotImplementedError

    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        if self.failure is not None:
            raise self.failure
        if self.response is None:
            raise AssertionError("Typed generation response was not configured")
        return self.response


@pytest.mark.asyncio
async def test_logged_generate_keeps_metadata_but_not_generation_payloads() -> None:
    capture = _Capture()
    provider = _Provider()

    result = await logged_generate(
        provider,
        caller="memory-summary",
        system_prompt="system-prompt-canary",
        messages=[{"role": "user", "content": "user-prompt-canary"}],
        model="test-model",
    )

    logs = capture.close()
    assert result == "raw-response-canary"
    assert "memory-summary" in logs
    assert "test-model" in logs
    assert "system-prompt-canary" not in logs
    assert "user-prompt-canary" not in logs
    assert "raw-response-canary" not in logs


@pytest.mark.asyncio
async def test_logged_generate_does_not_log_payloads_when_provider_raises() -> None:
    capture = _Capture()
    provider = _Provider()
    error = RuntimeError("provider-error-canary")
    provider.failure = error

    with pytest.raises(RuntimeError) as raised:
        await logged_generate(
            provider,
            caller="memory-facts",
            system_prompt="error-system-canary",
            messages=[{"role": "user", "content": "error-user-canary"}],
            model="error-model",
        )

    logs = capture.close()
    assert raised.value is error
    assert "memory-facts" in logs
    assert "error-model" in logs
    for canary in ("error-system-canary", "error-user-canary", "provider-error-canary"):
        assert canary not in logs


@pytest.mark.asyncio
async def test_dm_node_does_not_log_prompt_response_or_tool_arguments() -> None:
    capture = _Capture()
    provider = _Provider()
    provider.response = RawGenerationReceipt(
        text='{"text":"dm-response-canary"}',
        tool_calls=(
            GenerationToolReceipt(
                "call-1",
                "request_dice",
                RawToolArguments.raw_text(
                    '{"check":"tool-arguments-canary","stat":"DEX","difficulty":"normal"}'
                ),
            ),
        ),
    )
    state = {
        "step_count": 0,
        "max_agent_steps": 8,
        "world_state": {},
        "messages": [HumanMessage(content="dm-user-canary")],
        "system_prompt": "dm-system-canary",
        "campaign_id": "offline-campaign",
        "player_action": "dm-user-canary",
        "char_data": {},
        "world_baseline": {},
        "narration": "",
        "narration_segments": [],
        "npc_lines": [],
        "npc_beats": [],
        "user_id": "user",
    }

    async def generation_config(_user_id: str) -> tuple[_Provider, ModelConfig]:
        return provider, ModelConfig(
            provider="openai",
            model="dm-model",
            max_tokens=100,
            destination_fingerprint="test:destination",
        )

    try:
        with (
            patch(
                "app.core.dm.dm_nodes.get_user_generation",
                new=generation_config,
            ),
        ):
            await dm_node(cast(GameState, state), config={})
    finally:
        logs = capture.close()

    for canary in (
        "dm-system-canary",
        "dm-user-canary",
        "dm-response-canary",
        "tool-arguments-canary",
    ):
        assert canary not in logs
    assert "dm-model" in logs
    assert '"step": 0' in logs


@pytest.mark.asyncio
async def test_npc_generation_logs_static_caller_and_safe_failure_metadata() -> None:
    capture = _StructlogCapture()
    llm_capture = _Capture()
    provider = _Provider()
    provider.failure = RuntimeError("npc-provider-error-canary")
    npc_name = "npc-name-canary"

    with patch(
        "app.ai.npc_director.get_generation",
        new=lambda: _async_generation(provider),
    ):
        result = await invoke_single_npc(
            npc_name=npc_name,
            npc_profile={"name": npc_name},
            player_action="npc-action-canary",
            dm_narration="npc-context-canary",
        )

    logs = capture.close() + llm_capture.close()
    assert isinstance(result, NPCFailure)
    for canary in (
        npc_name,
        "npc-provider-error-canary",
        "npc-action-canary",
        "npc-context-canary",
    ):
        assert canary not in logs
    assert "npc_invoke_failed" in logs
    assert logs.count("npc_invoke_failed") == 1


@pytest.mark.asyncio
async def test_successful_npc_generation_does_not_log_name_or_payload() -> None:
    capture = _StructlogCapture()
    llm_capture = _Capture()
    provider = _Provider()
    provider.response = RawGenerationReceipt(
        text=(
            '{"status":"speaking","lines":["npc-response-canary"],'
            '"action":null,"axis_changes":[],"reveals_secret":false}'
        )
    )
    npc_name = "successful-npc-name-canary"

    with patch(
        "app.ai.npc_director.get_generation",
        new=lambda: _async_generation(provider),
    ):
        result = await invoke_single_npc(
            npc_name=npc_name,
            npc_profile={"name": npc_name},
            player_action="npc-success-action-canary",
            dm_narration="npc-success-context-canary",
        )

    logs = capture.close() + llm_capture.close()
    assert isinstance(result, NPCSpeaking)
    assert result.lines == ("npc-response-canary",)
    for canary in (
        npc_name,
        "npc-response-canary",
        "npc-success-action-canary",
        "npc-success-context-canary",
    ):
        assert canary not in logs
    assert "generation_output" not in logs


@pytest.mark.asyncio
async def test_parallel_npc_summary_logs_only_count() -> None:
    capture = _StructlogCapture()
    npc_names = ["batch-npc-canary-one", "batch-npc-canary-two"]
    actors = [NPCInput(name, {"name": name}, "hello") for name in npc_names]

    async def invoke(actor: NPCInput) -> NPCSpeaking:
        return NPCSpeaking(actor.npc_name, ("Hello.",))

    with patch("app.ai.npc_director._invoke_actor", side_effect=invoke):
        results = await invoke_npcs_parallel(actors, uuid.uuid4())

    logs = capture.close()
    assert len(results) == 2
    assert "npcs_invoked" in logs
    assert '"count": 2' in logs
    for name in npc_names:
        assert name not in logs


async def _async_generation(provider: _Provider) -> tuple[_Provider, ModelConfig]:
    return provider, ModelConfig(
        provider="openai",
        model="npc-test-model",
        max_tokens=100,
        destination_fingerprint="offline-test-destination",
    )


@pytest.mark.parametrize("capture_type", [_Capture, _StructlogCapture])
def test_capture_restores_logger_state_after_close(
    capture_type: type[_Capture | _StructlogCapture],
) -> None:
    original_npc_logger = npc_director.logger
    logger = logging.getLogger("llm_io" if capture_type is _Capture else "app.ai.npc_director")
    original_level = logger.level
    logger.setLevel(logging.WARNING)
    original_handlers = logger.handlers[:]
    capture = capture_type()

    try:
        capture.close()
        assert logger.level == logging.WARNING
        assert logger.handlers == original_handlers
        assert npc_director.logger is original_npc_logger
    finally:
        logger.setLevel(original_level)


@pytest.mark.parametrize("capture_type", [_Capture, _StructlogCapture])
def test_capture_restores_logger_state_when_close_raises(
    capture_type: type[_Capture | _StructlogCapture],
) -> None:
    original_npc_logger = npc_director.logger
    logger = logging.getLogger("llm_io" if capture_type is _Capture else "app.ai.npc_director")
    original_level = logger.level
    logger.setLevel(logging.WARNING)
    original_handlers = logger.handlers[:]
    capture = capture_type()

    try:
        with (
            patch.object(capture.handler, "flush", side_effect=RuntimeError("flush failed")),
            pytest.raises(RuntimeError, match="flush failed"),
        ):
            capture.close()
        assert logger.level == logging.WARNING
        assert logger.handlers == original_handlers
        assert npc_director.logger is original_npc_logger
    finally:
        logger.setLevel(original_level)
