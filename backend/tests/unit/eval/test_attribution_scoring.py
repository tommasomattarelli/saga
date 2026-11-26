from eval.attribution.manifest import (
    LIVE_MODEL,
    load_manifest,
    load_scenarios,
    prepare_manifest,
    validate_manifest,
)
from eval.attribution.scoring import overall, score_scenario

REAL_BATCH = "real_batch_anonymized"


def _evidence(*facts: dict[str, object], raw: str = "{}") -> dict[str, object]:
    return {
        "facts": list(facts),
        "raw": raw,
        "tokens": {"input": 3, "output": 1},
        "latency_ms": 12.0,
    }


def _fact(
    content: str, speaker: str, speaker_type: str, kind: str = "statement"
) -> dict[str, object]:
    return {
        "content": content,
        "assertion_type": kind,
        "entities": [{"name": speaker, "type": speaker_type}],
        "attribution": [0],
    }


def test_reporter_claim_and_npc_commitment_score_as_two_matched_facts() -> None:
    scenario = next(s for s in load_scenarios() if s.name == REAL_BATCH)
    score = score_scenario(
        scenario,
        _evidence(
            _fact(
                "The player told Vela that Kestrel swore the sealed charter lay under the "
                "third stair, wrapped in green wax.",
                "the player",
                "player",
            ),
            _fact(
                "Vela agreed to look for the charter beneath the third stair.",
                "Vela",
                "npc",
                "intention",
            ),
        ),
    )
    assert (score.matched, score.expected) == (2, 2)
    assert not score.hard_fail
    assert not score.extra_declarative


def test_wrong_speaker_and_bundled_claims_are_hard_failures() -> None:
    scenarios = {s.name: s for s in load_scenarios()}
    wrong = score_scenario(
        scenarios[REAL_BATCH],
        _evidence(
            _fact(
                "Vela said the charter under the third stair was sealed in green wax.",
                "Vela",
                "npc",
            )
        ),
    )
    assert wrong.wrong_speaker
    assert wrong.hard_fail

    bundled = score_scenario(
        scenarios["player_claim_npc_commitment"],
        _evidence(
            _fact(
                "The player told Vela that Kestrel swore the charter lay under the third stair, "
                "wrapped in green wax, and Vela will check it at dawn.",
                "the player",
                "player",
            )
        ),
    )
    assert bundled.bundled
    assert bundled.hard_fail
    assert overall((wrong, bundled), REAL_BATCH)["green"] is False


def test_manifest_preparation_and_validation_are_offline_and_sealed(tmp_path) -> None:
    manifest = prepare_manifest(run_id="offline-check")
    assert manifest.model == LIVE_MODEL
    assert manifest.request_cap == len(load_scenarios())
    validate_manifest(manifest)
    (tmp_path / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    assert load_manifest(tmp_path) == manifest
    changed = manifest.model_copy(update={"model": "other/free"})
    try:
        validate_manifest(changed)
    except ValueError as exc:
        assert "seal" in str(exc)
    else:
        raise AssertionError("a tampered manifest must not validate")
