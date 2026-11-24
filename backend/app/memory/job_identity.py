from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from app.ai.router import ModelConfig
from app.memory.batch_source_contracts import BatchInput
from app.memory.job_contracts import (
    MemoryGenerationIdentitySnapshot,
    MemoryJobExecutionIdentity,
    MemoryJobManifest,
)
from app.memory.job_requests import restore_job_requests
from app.memory.producer_prompts import PreparedMemoryRequest
from app.memory.producers import build_generation_request
from app.memory.production_policy import FactsPolicy

_session_scope: ContextVar[str | None] = ContextVar("memory_job_session_scope", default=None)


@contextmanager
def memory_job_session_scope(session_scope: str) -> Iterator[None]:
    token = _session_scope.set(session_scope)
    try:
        yield
    finally:
        _session_scope.reset(token)


def current_memory_job_session_scope() -> str | None:
    return _session_scope.get()


def config_from_identity(snapshot: MemoryGenerationIdentitySnapshot) -> ModelConfig:
    return ModelConfig(
        provider=snapshot.provider,
        model=snapshot.model,
        max_tokens=snapshot.output_limit.configured_ceiling,
        allow_json_mode_fallback=snapshot.allow_json_mode_fallback,
        allow_prompt_only_fallback=snapshot.allow_prompt_only_fallback,
        destination_fingerprint=snapshot.destination_fingerprint,
    )


def build_execution_identity(
    manifest: MemoryJobManifest,
    source: BatchInput,
    facts_policy: FactsPolicy,
    config: ModelConfig,
    max_sends: int,
    campaign_id: UUID,
    *,
    session_scope: str | None = None,
    openrouter_affinity_enabled: bool = True,
) -> MemoryJobExecutionIdentity:
    requests = restore_job_requests(manifest, source, facts_policy)
    session_affinity = effective_session_affinity(
        config.provider,
        session_scope or str(campaign_id),
        openrouter_affinity_enabled,
    )
    return build_request_identity(requests, config, max_sends, session_affinity)


def effective_session_affinity(
    provider: str, session_scope: str, openrouter_affinity_enabled: bool
) -> str | None:
    if provider == "openrouter" and openrouter_affinity_enabled:
        return session_scope
    return None


def build_request_identity(
    requests: tuple[PreparedMemoryRequest, ...],
    config: ModelConfig,
    max_sends: int,
    session_affinity: str | None,
) -> MemoryJobExecutionIdentity:
    snapshots: dict[str, MemoryGenerationIdentitySnapshot] = {}
    for prepared in requests:
        request = build_generation_request(prepared, config, session_affinity=session_affinity)
        snapshots[prepared.kind] = MemoryGenerationIdentitySnapshot.model_validate(
            {
                **json.loads(request.identity.snapshot_json),
                "request_identity_hash": request.identity.digest,
            }
        )
    return MemoryJobExecutionIdentity(
        result_identities=snapshots,
        max_sends_per_result=max_sends,
    )
