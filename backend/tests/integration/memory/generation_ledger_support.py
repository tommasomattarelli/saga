import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel

from app.ai.generation_contracts import GenerationRequest, OutputLimit, RawGenerationReceipt
from app.ai.generation_execution_ledger import (
    GenerationExecutionIdentity,
    GenerationRecoveryPolicy,
)
from app.ai.response_contracts import ResponseContract
from app.ai.response_validation import validate_response
from app.memory.job_claims import JobClaim
from app.memory.job_contracts import MemoryGenerationIdentitySnapshot, MemoryJobExecutionIdentity
from tests.integration.memory.job_support import job_sources, new_job
from tests.integration.memory.storage_support import HistoryFixture


class LedgerPayload(BaseModel):
    value: str


@dataclass(frozen=True)
class LedgerFixture:
    claim: JobClaim
    job_id: object
    identity: str
    request: GenerationRequest
    identities: dict[str, str]
    requests: dict[str, GenerationRequest]


def request_for(
    role: str, logical_result_id: str, *, allow_json_mode_fallback: bool = False
) -> GenerationRequest:
    return GenerationRequest.create(
        "Produce one value.",
        [{"role": "user", "content": "value"}],
        contract=ResponseContract("ledger_payload", "test-v1", LedgerPayload),
        provider="local",
        model="test-model",
        destination_fingerprint="destination-v1",
        role=role,
        logical_result_id=logical_result_id,
        output_limit=OutputLimit(configured_ceiling=512),
        allow_json_mode_fallback=allow_json_mode_fallback,
        contextual_validator_version="memory-context-summary-v1",
    )


def validate_receipt(receipt: RawGenerationReceipt, _request: GenerationRequest):
    if receipt.text is None:
        from app.ai.response_validation import (
            DiagnosticCode,
            ResponseValidationError,
            ValidationDiagnostic,
        )

        raise ResponseValidationError((ValidationDiagnostic(DiagnosticCode.MISSING, ("text",)),))
    return validate_response(receipt.text, _request.contract)


async def create_ledger_fixture(
    f: HistoryFixture,
    *,
    roles: tuple[str, ...] = ("summary",),
    allow_json_mode_fallback: bool = False,
):
    turns, batch, state = await job_sources(f)
    job = new_job(f, turns, batch, state, key=uuid4().hex + "0" * 32)
    requests = {
        role: request_for(
            role,
            f"{job.id}:{role}",
            allow_json_mode_fallback=allow_json_mode_fallback,
        )
        for role in roles
    }
    snapshots = {
        role: MemoryGenerationIdentitySnapshot.model_validate(
            {
                **json.loads(request.identity.snapshot_json),
                "request_identity_hash": request.identity.digest,
            }
        )
        for role, request in requests.items()
    }
    execution = MemoryJobExecutionIdentity(result_identities=snapshots, max_sends_per_result=3)
    token = uuid4()
    attempt_id = uuid4()
    expires = datetime.now(UTC) + timedelta(minutes=2)
    job.state = "running"
    job.attempt_count = 1
    job.cycle_attempt_count = 1
    job.claim_token = token
    job.lease_expires_at = expires
    job.execution_identity = execution
    job.execution_identity_hash = execution.digest(1)
    job.execution_identity_version = 1
    job.execution_contract_version = 1
    f.session.add(job)
    await f.session.flush()
    await f.session.execute(
        __import__("sqlalchemy").text(
            "INSERT INTO memory_job_attempts "
            "(id, job_id, campaign_id, attempt_number, retry_cycle, state, claim_token, started_at) "
            "VALUES (:id, :job, :campaign, 1, 0, 'started', :token, now())"
        ),
        {"id": attempt_id, "job": job.id, "campaign": job.campaign_id, "token": token},
    )
    await f.session.commit()
    claim = JobClaim(
        job_id=job.id,
        campaign_id=job.campaign_id,
        owner_id=f.campaign.user_id,
        attempt_id=attempt_id,
        token=token,
        batch_id=job.batch_id,
        manifest=job.manifest,
        policy=f.policy.payload,
    )
    identities = {
        role: GenerationExecutionIdentity.create(
            requests[role].identity, GenerationRecoveryPolicy(3)
        ).digest
        for role in roles
    }
    return LedgerFixture(
        claim,
        job.id,
        identities[roles[0]],
        requests[roles[0]],
        identities,
        requests,
    )
