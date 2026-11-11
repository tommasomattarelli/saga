import asyncio
from uuid import UUID, uuid4

from google.genai.errors import APIError as GoogleAPIError
from openai import APIStatusError

from app import dependencies
from app.ai.exceptions import PROVIDER_SDK_ERRORS, ContentPolicyError
from app.ai.generation_attempt import single_generation_attempt
from app.ai.generation_context import generation_context
from app.ai.router import ModelConfig, get_user_generation
from app.exceptions import ForbiddenError, UnauthorizedError, ValidationError
from app.memory.batch_input import load_batch_input
from app.memory.job_claims import JobClaim, claim_job, fail_claim, load_claim
from app.memory.job_publication import JobOutput, PublicationLeaseExpiredError, publish_job
from app.memory.job_requests import job_manifest_hash, restore_job_requests
from app.memory.producer_prompts import PreparedMemoryRequest
from app.memory.producers import generate_memory
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob


async def _requests(claim: JobClaim) -> tuple[PreparedMemoryRequest, ...]:
    async with dependencies.async_session() as db:
        job = await db.get(MemoryJob, claim.job_id)
        if job is None or job.manifest_hash != job_manifest_hash(claim.manifest):
            raise ValueError("The memory job manifest is invalid.")
        source = await load_batch_input(db, claim.campaign_id, claim.batch_id)
        requests = restore_job_requests(claim.manifest, source, claim.policy.facts)
        expected = ("summary", "facts") if job.kind == "batch" else ("global",)
        if tuple(request.kind for request in requests) != expected:
            raise ValueError("The memory job request roles are invalid.")
        return requests


async def _reserve_call(
    claim: JobClaim,
    request: PreparedMemoryRequest,
    config: ModelConfig,
) -> UUID | None:
    async with dependencies.async_session() as db:
        loaded = await load_claim(db, claim)
        if loaded is None:
            return None
        job, _, _ = loaded
        generation_id = uuid4()
        db.add(
            MemoryGeneration(
                id=generation_id,
                job_id=job.id,
                attempt_id=claim.attempt_id,
                campaign_id=claim.campaign_id,
                policy_id=job.policy_id,
                batch_id=job.batch_id,
                role=request.kind,
                provider=config.provider,
                model=config.model,
            )
        )
        await db.commit()
        return generation_id


async def _fail(
    claim: JobClaim,
    *,
    configuration_required: bool = False,
    uncertain: bool = False,
) -> None:
    async with dependencies.async_session() as db:
        await fail_claim(
            db, claim, configuration_required=configuration_required, uncertain=uncertain
        )
        await db.commit()


async def execute_job(campaign_id: UUID, job_id: UUID) -> bool:
    async with dependencies.async_session() as db:
        claim = await claim_job(db, campaign_id, job_id)
        await db.commit()
    if claim is None:
        return False
    try:
        requests = await _requests(claim)
    except ValueError:
        await _fail(claim, configuration_required=True)
        return False
    outputs = []
    try:
        # The deadline covers both specialists, not a fresh allowance for each call.
        async with asyncio.timeout(claim.policy.jobs.request_timeout_seconds):
            with single_generation_attempt():
                for request in requests:
                    provider, config = await get_user_generation(claim.owner_id)
                    generation_id = await _reserve_call(claim, request, config)
                    if generation_id is None:
                        return False
                    with generation_context((provider, config)):
                        result = await generate_memory(request)
                    outputs.append(JobOutput(generation_id=generation_id, raw=result.raw))
    except asyncio.CancelledError:
        await _fail(claim, uncertain=True)
        raise
    except (ValidationError, ForbiddenError, UnauthorizedError, ContentPolicyError):
        await _fail(claim, configuration_required=True)
        return False
    except PROVIDER_SDK_ERRORS as exc:
        status = (
            exc.status_code
            if isinstance(exc, APIStatusError)
            else (exc.code if isinstance(exc, GoogleAPIError) else None)
        )
        await _fail(claim, configuration_required=status in {401, 403, 404})
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
