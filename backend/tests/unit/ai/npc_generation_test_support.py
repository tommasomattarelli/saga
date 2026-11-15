from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt
from app.ai.generation_execution_ledger import (
    GenerationExecutionIdentity,
    GenerationRecoveryPolicy,
    InMemoryGenerationLedger,
)
from app.ai.npc_director import invoke_single_npc
from app.ai.npc_outcomes import NPCResult
from app.ai.router import ModelConfig
from app.models.psychology import PsychologyDef
from tests.unit.eval.dialogue.typed_provider_test_support import TypedResponseProvider


def response(
    status: str = "speaking",
    lines: list[str] | None = None,
    axis_changes: dict[str, object] | None = None,
    *,
    wire_entries: bool = True,
) -> RawGenerationReceipt:
    axes = {} if axis_changes is None else axis_changes
    return RawGenerationReceipt(
        text=json.dumps(
            {
                "status": status,
                "lines": ["Hello."] if lines is None else lines,
                "action": None,
                "axis_changes": (
                    [{"key": key, "value": value} for key, value in axes.items()]
                    if wire_entries
                    else axes
                ),
                "reveals_secret": False,
            }
        )
    )


class RecordingGenerationLedger(InMemoryGenerationLedger):
    def __init__(self, instances: list[InMemoryGenerationLedger]) -> None:
        super().__init__()
        instances.append(self)


def execution_identity(request: GenerationRequest, max_sends: int) -> str:
    return GenerationExecutionIdentity.create(
        request.identity, GenerationRecoveryPolicy(max_sends)
    ).digest


async def invoke_with(
    monkeypatch: pytest.MonkeyPatch,
    provider: TypedResponseProvider,
    *,
    budget: int = 3,
    npc_name: str = "Lyra",
    allow_json_mode_fallback: bool = False,
    allow_prompt_only_fallback: bool = False,
    psychology: PsychologyDef | None = None,
) -> NPCResult:
    monkeypatch.setattr(
        "app.ai.npc_director.get_generation",
        AsyncMock(
            return_value=(
                provider,
                ModelConfig(
                    "openai",
                    "test-model",
                    256,
                    allow_json_mode_fallback=allow_json_mode_fallback,
                    allow_prompt_only_fallback=allow_prompt_only_fallback,
                    destination_fingerprint="offline-test-destination",
                ),
            )
        ),
    )
    from app.ai.generation_execution_ledger import GenerationRecoveryPolicy

    monkeypatch.setattr(
        "app.ai.npc_director.get_generation_recovery_policy",
        lambda: GenerationRecoveryPolicy(budget),
    )
    result = await invoke_single_npc(
        npc_name,
        {"name": npc_name},
        "Hello",
        "A clearing.",
        psychology=psychology,
    )
    return result
