from __future__ import annotations

from pathlib import Path
from uuid import UUID

from eval.integrated_memory.plan import IntegratedPlan, validate_plan, write_plan
from eval.support.run_lock import evidence_run_lock


async def run_plan(
    plan: IntegratedPlan, directory: Path, owner: UUID, *, authorized: bool
) -> None:
    if not authorized:
        raise ValueError("live integrated evaluation requires explicit owner authorization")
    validate_plan(plan)
    if not plan.executable:
        raise ValueError(
            "integrated evaluation gates are incomplete: " + ", ".join(plan.missing_gates)
        )
    directory.mkdir(parents=True, exist_ok=True)
    with evidence_run_lock(directory):
        write_plan(plan, directory)
        if any(
            (directory / name).exists()
            for name in ("run-start.json", "run.json", "requests.jsonl")
        ):
            raise ValueError(
                "existing integrated run requires review; automatic replay is disabled"
            )
        from eval.integrated_memory.execution import execute_plan

        await execute_plan(plan, directory, owner)
