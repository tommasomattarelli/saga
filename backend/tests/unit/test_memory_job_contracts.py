import uuid

import pytest
from pydantic import ValidationError

from app.memory.job_contracts import MemoryJobManifest


def test_manifest_is_typed_frozen_and_preserves_ordered_sources() -> None:
    source_ids = [uuid.uuid4(), uuid.uuid4()]
    manifest = MemoryJobManifest(
        instruction_text="Summarize the source turns.",
        instruction_version="prompt-v1",
        source_turn_ids=tuple(source_ids),
        source_hash="a" * 64,
        language="en",
    )

    assert manifest.source_turn_ids == tuple(source_ids)
    assert MemoryJobManifest.model_validate(manifest.model_dump(mode="json")) == manifest
    with pytest.raises(ValidationError):
        manifest.instruction_version = "prompt-v2"


def test_manifest_rejects_extra_fields_and_invalid_hash() -> None:
    with pytest.raises(ValidationError):
        MemoryJobManifest(
            instruction_text="Summarize.",
            instruction_version="prompt-v1",
            source_turn_ids=(uuid.uuid4(),),
            source_hash="not-a-sha256",
            language="en",
            provider="must-not-be-in-the-manifest",
        )


def test_manifest_rejects_untyped_source_ids() -> None:
    with pytest.raises(ValidationError):
        MemoryJobManifest(
            instruction_text="Summarize.",
            instruction_version="prompt-v1",
            source_turn_ids=("turn-1",),
            source_hash="b" * 64,
            language="en",
        )
