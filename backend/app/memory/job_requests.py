from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from app.memory.batch_source_contracts import BatchInput
from app.memory.document_contracts import GlobalPayload
from app.memory.job_contracts import MemoryJobManifest
from app.memory.producer_prompts import (
    PRODUCER_VERSION,
    PreparedMemoryRequest,
    canonical,
    digest,
    prepare_request,
)
from app.memory.production_policy import FactsPolicy, GlobalPolicy

INSTRUCTION_VERSION: Literal["memory-requests-v1"] = "memory-requests-v1"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _FrozenRequest(_FrozenModel):
    kind: Literal["summary", "facts", "global"]
    system_prompt: StrictStr = Field(min_length=1)
    user_prompt: StrictStr = Field(min_length=1)
    source_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    instruction_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class _InstructionEnvelope(_FrozenModel):
    instruction_version: Literal["memory-requests-v1"]
    job_kind: Literal["batch", "global"]
    producer_version: StrictStr = Field(min_length=1)
    requests: tuple[_FrozenRequest, ...] = Field(min_length=1)


def _encode(requests: tuple[PreparedMemoryRequest, ...], kind: Literal["batch", "global"]) -> str:
    frozen_requests: list[_FrozenRequest] = []
    for request in requests:
        assert request.kind != "batch"
        frozen_requests.append(
            _FrozenRequest(
                kind=request.kind,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                source_hash=request.source_hash,
                instruction_hash=request.instruction_hash,
            )
        )
    envelope = _InstructionEnvelope(
        instruction_version=INSTRUCTION_VERSION,
        job_kind=kind,
        producer_version=PRODUCER_VERSION,
        requests=tuple(frozen_requests),
    )
    return envelope.model_dump_json()


def build_job_manifest(
    kind: Literal["batch", "global"],
    source: BatchInput,
    *,
    language: str,
    facts_policy: FactsPolicy,
    global_policy: GlobalPolicy | None = None,
    previous: GlobalPayload | None = None,
) -> MemoryJobManifest:
    requests: tuple[PreparedMemoryRequest, ...]
    if kind == "batch":
        if global_policy is not None or previous is not None:
            raise ValueError("Batch jobs do not accept global-generation inputs.")
        requests = (
            prepare_request("summary", source, language=language, facts_policy=facts_policy),
            prepare_request("facts", source, language=language, facts_policy=facts_policy),
        )
    else:
        requests = (
            prepare_request(
                "global",
                source,
                language=language,
                facts_policy=facts_policy,
                global_policy=global_policy,
                previous=previous,
            ),
        )
    return MemoryJobManifest(
        instruction_text=_encode(requests, kind),
        instruction_version=INSTRUCTION_VERSION,
        source_turn_ids=tuple(turn.turn_id for turn in source.turns),
        source_hash=source.source_hash(),
        language=language,
    )


def restore_job_requests(
    manifest: MemoryJobManifest,
    source: BatchInput,
    facts_policy: FactsPolicy,
) -> tuple[PreparedMemoryRequest, ...]:
    if manifest.instruction_version != INSTRUCTION_VERSION:
        raise ValueError("Unsupported memory instruction version.")
    if manifest.source_hash != source.source_hash():
        raise ValueError("Memory job source hash does not match its source.")
    if manifest.source_turn_ids != tuple(turn.turn_id for turn in source.turns):
        raise ValueError("Memory job source IDs do not match its source.")
    try:
        json.loads(manifest.instruction_text, object_pairs_hook=_unique_object)
        envelope = _InstructionEnvelope.model_validate_json(manifest.instruction_text)
    except (ValidationError, ValueError) as exc:
        raise ValueError("Invalid frozen memory instruction envelope.") from exc
    expected: tuple[str, ...] = (
        ("summary", "facts") if envelope.job_kind == "batch" else ("global",)
    )
    if tuple(request.kind for request in envelope.requests) != expected:
        raise ValueError("Frozen memory request roles do not match job kind.")
    if len(envelope.requests) != len(expected):
        raise ValueError("Frozen memory request count does not match job kind.")
    restored: list[PreparedMemoryRequest] = []
    for request in envelope.requests:
        if (
            digest(envelope.producer_version + "\n" + request.system_prompt)
            != request.instruction_hash
        ):
            raise ValueError("Frozen memory instruction hash is invalid.")
        _validate_request_evidence(
            request, envelope.job_kind, source, facts_policy, manifest.language
        )
        restored.append(
            PreparedMemoryRequest(
                kind=request.kind,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                source=source,
                facts_policy=facts_policy,
                source_hash=request.source_hash,
                instruction_hash=request.instruction_hash,
            )
        )
    return tuple(restored)


def _validate_request_evidence(
    request: _FrozenRequest,
    job_kind: Literal["batch", "global"],
    source: BatchInput,
    facts_policy: FactsPolicy,
    language: str,
) -> None:
    try:
        evidence = json.loads(request.user_prompt, object_pairs_hook=_unique_object)
    except (ValueError, TypeError) as exc:
        raise ValueError("Frozen memory request evidence is invalid.") from exc
    if not isinstance(evidence, dict):
        raise ValueError("Frozen memory request evidence is invalid.")
    expected_keys = {"language", "facts_policy", "global_policy", "source"}
    if job_kind == "global":
        expected_keys.add("previous")
    if set(evidence) != expected_keys or evidence["language"] != language:
        raise ValueError("Frozen memory request settings are inconsistent.")
    if canonical(evidence["facts_policy"]) != canonical(facts_policy.model_dump(mode="json")):
        raise ValueError("Frozen memory facts policy does not match.")
    if canonical(evidence["source"]) != canonical(source.model_dump(mode="json")):
        raise ValueError("Frozen memory request source does not match.")
    global_policy: GlobalPolicy | None = None
    previous: GlobalPayload | None = None
    if job_kind == "batch":
        if evidence["global_policy"] is not None:
            raise ValueError("Batch request cannot include a global policy.")
        evidence_for_hash: dict[str, object] = {"source": source.model_dump(mode="json")}
        expected_hash = source.source_hash()
    else:
        if evidence["global_policy"] is None:
            raise ValueError("Global request requires a global policy.")
        try:
            global_policy = GlobalPolicy.model_validate_json(canonical(evidence["global_policy"]))
            previous = (
                GlobalPayload.model_validate_json(canonical(evidence["previous"]))
                if evidence["previous"] is not None
                else None
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise ValueError("Frozen global request settings are invalid.") from exc
        evidence_for_hash = {
            "source": source.model_dump(mode="json"),
            "previous": previous.model_dump(mode="json") if previous else None,
        }
        expected_hash = digest(canonical(evidence_for_hash))
    if request.source_hash != expected_hash:
        raise ValueError("Frozen memory request source hash is invalid.")
    expected_prompt = canonical(
        {
            "language": language,
            "facts_policy": facts_policy.model_dump(mode="json"),
            "global_policy": global_policy.model_dump(mode="json") if global_policy else None,
            **evidence_for_hash,
        }
    )
    if request.user_prompt != expected_prompt:
        raise ValueError("Frozen memory request prompt is inconsistent with its evidence.")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def job_manifest_hash(manifest: MemoryJobManifest) -> str:
    return digest(canonical(manifest.model_dump(mode="json")))
