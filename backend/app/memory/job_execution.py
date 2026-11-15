import asyncio
from collections.abc import Callable
from copy import copy
from typing import Literal, cast
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from app import dependencies
from app.ai.credentials import resolve_generation
from app.ai.generation_errors import Adapter
from app.ai.generation_execution import GenerationExecutionError, GenerationProvider
from app.ai.generation_execution_ledger import GenerationRecoveryPolicy
from app.ai.providers.base import AIProvider, get_provider
from app.ai.providers.local import LocalProvider
from app.ai.router import ModelConfig
from app.ai.session_affinity import campaign_session
from app.config_loader import load_saga_config
from app.exceptions import ForbiddenError, UnauthorizedError, ValidationError
from app.memory.batch_input import load_batch_input
from app.memory.generation_ledger import DurableMemoryGenerationLedger
from app.memory.job_claim_transitions import INCOMPATIBLE_JOB_REASON
from app.memory.job_claims import JobClaim, claim_job, fail_claim
from app.memory.job_identity import build_execution_identity
from app.memory.job_publication import JobOutput, PublicationLeaseExpiredError, publish_job
from app.memory.job_requests import job_manifest_hash, restore_job_requests
from app.memory.producer_prompts import PreparedMemoryRequest
from app.memory.producers import execute_memory_generation
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob
from app.models.user import User

ProviderDecorator = Callable[
    [AIProvider, ModelConfig, JobClaim, tuple[PreparedMemoryRequest, ...]],
    GenerationProvider,
]


class IncompatibleMemoryJobError(Exception):
    pass


class MemoryJobConfigurationError(Exception):
    pass


def _bind_frozen_affinity(provider: AIProvider, session_affinity: str | None) -> AIProvider:
    if not isinstance(provider, LocalProvider):
        if session_affinity is not None:
            raise MemoryJobConfigurationError
        return provider
    if session_affinity is not None:
        isolated = copy(provider)
        isolated.client = provider.client.with_options(
            default_headers={"x-session-id": session_affinity}
        )
        provider = isolated
    if provider.client.default_headers.get("x-session-id") != session_affinity:
        raise MemoryJobConfigurationError
    return provider


async def _runtime(
    claim: JobClaim,
    provider_decorator: ProviderDecorator | None,
    session_scope: str | None,
) -> tuple[tuple[PreparedMemoryRequest, ...], GenerationProvider, ModelConfig, int, str | None]:
    async with dependencies.async_session() as db:
        job = await db.get(MemoryJob, claim.job_id)
        if (
            job is None
            or job.manifest_hash != job_manifest_hash(claim.manifest)
            or job.execution_contract_version != 1
            or job.execution_identity is None
            or job.execution_identity_hash is None
            or job.execution_identity_version is None
        ):
            raise IncompatibleMemoryJobError
        frozen = job.execution_identity
        try:
            frozen.verify(job.execution_identity_version, job.execution_identity_hash)
        except ValueError:
            raise IncompatibleMemoryJobError from None

        try:
            source = await load_batch_input(db, claim.campaign_id, claim.batch_id)
            requests = restore_job_requests(claim.manifest, source, claim.policy.facts)
        except (PydanticValidationError, ValueError):
            raise IncompatibleMemoryJobError from None
        roles = ("summary", "facts") if job.kind == "batch" else ("global",)
        if tuple(request.kind for request in requests) != roles or set(
            frozen.result_identities
        ) != set(roles):
            raise IncompatibleMemoryJobError

        user = await db.get(User, claim.owner_id)
        if user is None:
            raise MemoryJobConfigurationError
        try:
            config, key, base_url = resolve_generation(user)
        except ValidationError:
            raise MemoryJobConfigurationError from None
        generation_config = load_saga_config().get("generation", {})
        affinity_enabled = generation_config.get("openrouter_session_affinity", True)
        if not isinstance(affinity_enabled, bool):
            raise MemoryJobConfigurationError
        target_scope = session_scope or str(claim.campaign_id)
        try:
            current = build_execution_identity(
                claim.manifest,
                source,
                claim.policy.facts,
                config,
                frozen.max_sends_per_result,
                claim.campaign_id,
                session_scope=target_scope,
                openrouter_affinity_enabled=affinity_enabled,
            )
        except (PydanticValidationError, ValueError):
            raise IncompatibleMemoryJobError from None
        if current.model_dump(mode="json") != frozen.model_dump(mode="json"):
            raise MemoryJobConfigurationError
        affinities = {snapshot.session_affinity for snapshot in frozen.result_identities.values()}
        if len(affinities) != 1:
            raise IncompatibleMemoryJobError
        session_affinity = next(iter(affinities))
        max_sends = frozen.max_sends_per_result

    provider: AIProvider = get_provider(config.provider, api_key=key, base_url=base_url)
    provider = _bind_frozen_affinity(provider, session_affinity)
    generation_provider: GenerationProvider = provider
    if provider_decorator is not None:
        generation_provider = provider_decorator(provider, config, claim, requests)
    return requests, generation_provider, config, max_sends, session_affinity


async def _fail(
    claim: JobClaim,
    *,
    configuration_required: bool = False,
    uncertain: bool = False,
    blocked_reason: str | None = None,
) -> None:
    async with dependencies.async_session() as db:
        await fail_claim(
            db,
            claim,
            configuration_required=configuration_required,
            uncertain=uncertain,
            blocked_reason=blocked_reason,
        )
        await db.commit()


async def _configuration_failure(claim: JobClaim) -> bool:
    async with dependencies.async_session() as db:
        return (
            await db.scalar(
                select(MemoryGeneration.id).where(
                    MemoryGeneration.job_id == claim.job_id,
                    MemoryGeneration.attempt_id == claim.attempt_id,
                    MemoryGeneration.status == "stop",
                    MemoryGeneration.outcome_reason == "provider_request_rejected",
                )
            )
        ) is not None


async def execute_job(
    campaign_id: UUID,
    job_id: UUID,
    *,
    provider_decorator: ProviderDecorator | None = None,
    session_scope: str | None = None,
) -> bool:
    with campaign_session(campaign_id):
        if provider_decorator is None and session_scope is None:
            return await _execute_job(campaign_id, job_id)
        return await _execute_job(campaign_id, job_id, provider_decorator, session_scope)


async def _execute_job(
    campaign_id: UUID,
    job_id: UUID,
    provider_decorator: ProviderDecorator | None = None,
    session_scope: str | None = None,
) -> bool:
    async with dependencies.async_session() as db:
        claim = await claim_job(db, campaign_id, job_id)
        await db.commit()
    if claim is None:
        return False

    try:
        requests, provider, config, max_sends, session_affinity = await _runtime(
            claim, provider_decorator, session_scope
        )
    except MemoryJobConfigurationError:
        await _fail(claim, configuration_required=True)
        return False
    except IncompatibleMemoryJobError:
        await _fail(claim, blocked_reason=INCOMPATIBLE_JOB_REASON)
        return False

    outputs = []
    ledger = DurableMemoryGenerationLedger(claim)
    try:
        async with asyncio.timeout(claim.policy.jobs.request_timeout_seconds):
            for request in requests:
                result = await execute_memory_generation(
                    request,
                    provider=provider,
                    ledger=ledger,
                    config=config,
                    policy=GenerationRecoveryPolicy(max_sends),
                    adapter=Adapter(config.provider),
                    session_affinity=session_affinity,
                )
                outputs.append(
                    JobOutput(
                        role=cast(Literal["summary", "facts", "global"], request.kind),
                        send_number=result.send_number,
                    )
                )
    except asyncio.CancelledError:
        await _fail(claim, uncertain=True)
        raise
    except TimeoutError:
        await _fail(claim, uncertain=True)
        return False
    except (ValidationError, ForbiddenError, UnauthorizedError):
        await _fail(claim, configuration_required=True)
        return False
    except GenerationExecutionError:
        await _fail(claim, configuration_required=await _configuration_failure(claim))
        return False
    except Exception:
        await _fail(claim)
        return False

    try:
        async with dependencies.async_session() as db:
            published = await publish_job(db, claim, tuple(outputs))
            await db.commit()
            return published
    except PublicationLeaseExpiredError:
        return False
