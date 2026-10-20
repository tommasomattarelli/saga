"""Response schemas for the campaign embedding-index lifecycle API (ADR 0018 B)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class EmbeddingIndexSummary(BaseModel):
    id: uuid.UUID
    provider: str
    model: str
    endpoint_name: str | None
    pipeline_version: str
    dimension: int | None
    state: str
    last_error: str | None


class EmbeddingIndexProgress(BaseModel):
    total: int
    embedded: int
    pending: int
    failed: int
    turn_total: int
    fact_total: int


class EmbeddingIndexStatus(BaseModel):
    active: EmbeddingIndexSummary | None
    target: EmbeddingIndexSummary | None
    latest: EmbeddingIndexSummary | None
    progress: EmbeddingIndexProgress | None
    suspended_reason: str | None
    needs_retry: bool
