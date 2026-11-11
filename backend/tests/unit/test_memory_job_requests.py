import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.memory.batch_source_contracts import BatchInput
from app.memory.document_contracts import GlobalPayload
from app.memory.production_policy import FactsPolicy, GlobalPolicy


def source(action: str = "Ask Mira about the key") -> BatchInput:
    return BatchInput.model_validate(
        {
            "turns": (
                {
                    "reference": "t1",
                    "turn_id": uuid4(),
                    "player_action": action,
                    "narration": "Mira hid the key.",
                    "operations": None,
                },
            )
        }
    )


def facts_policy() -> FactsPolicy:
    return FactsPolicy.model_validate(
        {
            "max_per_batch": 4,
            "importance_levels": [
                {"name": "major", "criteria": "Changes the campaign", "examples": "A betrayal"}
            ],
        }
    )


def test_batch_round_trip_freezes_two_ordered_specialists() -> None:
    from app.memory.job_requests import build_job_manifest, job_manifest_hash, restore_job_requests

    batch = source()
    manifest = build_job_manifest("batch", batch, language="it", facts_policy=facts_policy())
    restored = restore_job_requests(manifest, batch, facts_policy())
    assert [request.kind for request in restored] == ["summary", "facts"]
    assert manifest.source_turn_ids == (batch.turns[0].turn_id,)
    assert manifest.source_hash == batch.source_hash()
    assert job_manifest_hash(manifest) != job_manifest_hash(
        manifest.model_copy(update={"language": "en"})
    )
    assert all(request.user_prompt and request.system_prompt for request in restored)


def test_global_round_trip_and_templates_are_not_read_during_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.prompts import loader
    from app.memory import job_requests, producer_prompts

    batch = source()
    manifest = job_requests.build_job_manifest(
        "global",
        batch,
        language="en",
        facts_policy=facts_policy(),
        global_policy=GlobalPolicy(target_words=200),
        previous=GlobalPayload(
            story_so_far="A journey begins.",
            open_threads=(),
            relationships=(),
            resolved_threads=(),
        ),
    )
    monkeypatch.setattr(
        job_requests, "prepare_request", lambda *args, **kwargs: pytest.fail("templates reread")
    )
    monkeypatch.setattr(loader, "template", lambda *args, **kwargs: pytest.fail("template reread"))
    monkeypatch.setattr(producer_prompts, "PRODUCER_VERSION", "changed-producer-v99")
    monkeypatch.setattr(job_requests, "PRODUCER_VERSION", "changed-producer-v99")
    restored = job_requests.restore_job_requests(manifest, batch, facts_policy())
    assert [request.kind for request in restored] == ["global"]
    assert "A journey begins." in restored[0].user_prompt


def test_restore_rejects_changed_prompt_evidence_and_request_hash() -> None:
    import json

    from app.memory.job_requests import build_job_manifest, restore_job_requests

    batch = source()
    manifest = build_job_manifest("batch", batch, language="it", facts_policy=facts_policy())
    envelope = json.loads(manifest.instruction_text)
    altered_prompt = json.loads(envelope["requests"][0]["user_prompt"])
    altered_prompt["language"] = "en"
    envelope["requests"][0]["user_prompt"] = json.dumps(altered_prompt)
    with pytest.raises(ValueError):
        restore_job_requests(
            manifest.model_copy(update={"instruction_text": json.dumps(envelope)}),
            batch,
            facts_policy(),
        )

    envelope = json.loads(manifest.instruction_text)
    envelope["requests"][0]["source_hash"] = "0" * 64
    with pytest.raises(ValueError):
        restore_job_requests(
            manifest.model_copy(update={"instruction_text": json.dumps(envelope)}),
            batch,
            facts_policy(),
        )


def test_global_restore_rejects_changed_previous_payload_or_source_hash() -> None:
    import json

    from app.memory.job_requests import build_job_manifest, restore_job_requests

    batch = source()
    manifest = build_job_manifest(
        "global",
        batch,
        language="en",
        facts_policy=facts_policy(),
        global_policy=GlobalPolicy(target_words=200),
        previous=GlobalPayload(
            story_so_far="A journey begins.",
            open_threads=(),
            relationships=(),
            resolved_threads=(),
        ),
    )
    envelope = json.loads(manifest.instruction_text)
    payload = json.loads(envelope["requests"][0]["user_prompt"])
    payload["previous"]["story_so_far"] = "Altered history."
    envelope["requests"][0]["user_prompt"] = json.dumps(payload)
    altered = manifest.model_copy(update={"instruction_text": json.dumps(envelope)})
    with pytest.raises(ValueError):
        restore_job_requests(altered, batch, facts_policy())

    envelope = json.loads(manifest.instruction_text)
    envelope["requests"][0]["source_hash"] = "0" * 64
    with pytest.raises(ValueError):
        restore_job_requests(
            manifest.model_copy(update={"instruction_text": json.dumps(envelope)}),
            batch,
            facts_policy(),
        )


def test_restore_rejects_changed_source_version_hash_and_role() -> None:
    from app.memory.job_requests import build_job_manifest, restore_job_requests

    batch = source()
    manifest = build_job_manifest("batch", batch, language="it", facts_policy=facts_policy())
    with pytest.raises(ValueError):
        restore_job_requests(manifest, source("Open the door"), facts_policy())
    for changed in (
        manifest.model_copy(update={"instruction_version": "unknown-v9"}),
        manifest.model_copy(update={"source_hash": "0" * 64}),
        manifest.model_copy(
            update={
                "instruction_text": manifest.instruction_text.replace('"summary"', '"global"', 1)
            }
        ),
    ):
        with pytest.raises((ValueError, ValidationError)):
            restore_job_requests(changed, batch, facts_policy())


def test_envelope_rejects_extras_and_manifest_has_no_credentials() -> None:
    from app.memory.job_requests import build_job_manifest

    manifest = build_job_manifest("batch", source(), language="it", facts_policy=facts_policy())
    assert "api_key" not in manifest.instruction_text.lower()
    envelope = json.loads(manifest.instruction_text)
    with pytest.raises((ValueError, ValidationError)):
        envelope["unexpected"] = True
        # Parsing is validated by restore, which accepts only the strict versioned shape.
        from app.memory.job_requests import restore_job_requests

        restore_job_requests(
            manifest.model_copy(update={"instruction_text": json.dumps(envelope)}),
            source(),
            facts_policy(),
        )
