from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from time import monotonic
from unittest.mock import patch
from uuid import UUID

from app import dependencies
from app.ai.generation_context import Generation
from app.memory import job_execution
from app.memory.batch_input import load_batch_input
from app.memory.job_scheduler import coordinate_memory
from app.memory.producer_prompts import PreparedMemoryRequest
from app.memory.producers import MemoryGeneration, generate_memory
from app.models.memory_job import MemoryJob
from eval.integrated_memory.evidence_io import append_json, provider_evidence
from eval.integrated_memory.ledger import AttemptScope, IntegratedLedger
from eval.integrated_memory.plan import IntegratedPlan
from eval.support.dialogue_affinity import session_id_for_model
from eval.support.provider_trace import ProviderTrace

GenerationResolver = Callable[[UUID], Awaitable[Generation]]


class MemoryDriver:
    def __init__(
        self,
        plan: IntegratedPlan,
        ledger: IntegratedLedger,
        campaign_id: UUID,
        directory: Path,
        resolve: GenerationResolver,
    ) -> None:
        self.plan = plan
        self.ledger = ledger
        self.campaign_id = campaign_id
        self.directory = directory
        self.resolve = resolve

    async def drain(self) -> None:
        for _ in range(self.plan.batch_count + self.plan.global_count + 1):
            self.ledger.ensure_healthy()
            async with dependencies.async_session() as db:
                jobs = await coordinate_memory(db, self.campaign_id)
                await db.commit()
            if not jobs:
                return
            for job_id in jobs:
                await self._job(job_id)
        raise ValueError("integrated memory scheduling exceeded the planned transition bound")

    async def _job(self, job_id: UUID) -> None:
        async with dependencies.async_session() as db:
            job = await db.get(MemoryJob, job_id)
            if job is None or job.campaign_id != self.campaign_id:
                raise ValueError("integrated evaluation job identity changed")
            if job.attempt_count or job.state != "queued":
                raise ValueError("integrated evaluation stops before retrying a memory job")
            batch_id = job.batch_id
            source = await load_batch_input(db, self.campaign_id, batch_id)
            if tuple(turn.turn_id for turn in source.turns) != job.manifest.source_turn_ids:
                raise ValueError("persisted job sources differ from batch membership")
        trace: ProviderTrace | None = None

        async def resolve(owner: UUID | str) -> Generation:
            nonlocal trace
            provider, config = await self.resolve(UUID(str(owner)))
            trace = ProviderTrace(provider)
            return trace, config

        async def generate(request: PreparedMemoryRequest) -> MemoryGeneration:
            if request.source != source:
                raise ValueError("evaluated request differs from the persisted batch input")
            if request.kind == "batch":
                raise ValueError("production jobs must use specialist requests")
            if trace is not None:
                trace.role = f"memory_{request.kind}"
            scope = AttemptScope(
                run_id=self.plan.run_id,
                campaign_id=self.campaign_id,
                job_id=job_id,
                batch_id=batch_id,
                source_turn_ids=tuple(turn.turn_id for turn in source.turns),
                input_hash=request.source_hash,
                role=request.kind,
                provider="openrouter",
                model=self.plan.generation_model or "",
            )
            append_json(
                self.directory / "inputs.jsonl",
                {
                    "scope": scope.model_dump(mode="json"),
                    "source": source.model_dump(mode="json"),
                    "system_prompt": request.system_prompt,
                    "user_prompt": request.user_prompt,
                    "instruction_hash": request.instruction_hash,
                    "request_headers": {
                        "x-session-id": session_id_for_model(
                            self.plan.session_scope, self.plan.generation_model or ""
                        )
                    },
                },
            )
            started = monotonic()
            try:
                with self.ledger.scope(scope):
                    result = await generate_memory(request)
            except BaseException:
                raw = trace.response.get("text", "") if trace else ""
                append_json(
                    self.directory / "outputs.jsonl",
                    {
                        "scope": scope.model_dump(mode="json"),
                        "raw": str(raw),
                        "valid": False,
                        **provider_evidence(trace, monotonic() - started),
                    },
                )
                raise
            append_json(
                self.directory / "outputs.jsonl",
                {
                    "scope": scope.model_dump(mode="json"),
                    "raw": result.raw,
                    "valid": True,
                    **provider_evidence(trace, monotonic() - started),
                },
            )
            return result

        with (
            patch.object(job_execution, "get_user_generation", resolve),
            patch.object(job_execution, "generate_memory", generate),
        ):
            published = await job_execution.execute_job(self.campaign_id, job_id)
        self.ledger.ensure_healthy()
        if not published:
            raise ValueError("memory job did not publish; review evidence before any retry")
