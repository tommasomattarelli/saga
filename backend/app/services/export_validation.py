from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.schemas.campaign_export import CampaignExport
from app.services.export_history_validation import validate_history
from app.services.export_integrity import (
    ExportIntegrityError,
    _require,
    _unique,
)
from app.services.export_job_validation import validate_jobs
from app.services.export_memory_validation import validate_memory
from app.services.export_selection_validation import validate_selections


class _OwnedRow(Protocol):
    campaign_id: UUID


class _CampaignRow(_OwnedRow, Protocol):
    id: UUID


def validate_campaign_export(archive: CampaignExport) -> None:
    campaign_id = archive.campaign.id
    tables: tuple[tuple[str, Sequence[_CampaignRow]], ...] = (
        ("turn", archive.turns),
        ("continuation", archive.continuations),
        ("save", archive.saves),
        ("policy", archive.memory_policies),
        ("state", archive.memory_states),
        ("batch", archive.memory_batches),
        ("summary", archive.memory_summaries),
        ("checkpoint", archive.global_checkpoints),
        ("fact", archive.memory_facts),
        ("generation", archive.generations),
        ("job", archive.jobs),
        ("attempt", archive.job_attempts),
    )
    for label, rows in tables:
        _unique(rows, lambda row: row.id, label)
    owned_tables: tuple[tuple[str, Sequence[_OwnedRow]], ...] = (
        *tables,
        ("turn operation", archive.turn_operations),
        ("batch turn", archive.batch_turns),
        ("fact source", archive.fact_sources),
    )
    for label, owned in owned_tables:
        _require(
            all(row.campaign_id == campaign_id for row in owned),
            f"{label.title()} belongs to another campaign.",
        )
    validate_history(archive)
    validate_memory(archive)
    validate_jobs(archive)
    validate_selections(archive)


__all__ = ["ExportIntegrityError", "validate_campaign_export"]
