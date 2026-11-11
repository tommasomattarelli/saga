import hashlib
import json

import pytest
from pydantic import ValidationError

from app.memory.production_policy import MemoryProductionPolicy


def policy_data() -> dict[str, object]:
    return {
        "raw_turns": 8,
        "batch_turns": 4,
        "intermediate_limit": 2,
        "backlog_batches": 1,
        "facts": {
            "max_per_batch": 3,
            "importance_levels": [
                {"name": "ordinary", "criteria": "Relevant event", "examples": "A clue"},
                {"name": "critical", "criteria": "Major event", "examples": "A betrayal"},
            ],
        },
        "global": {"target_words": 500},
        "jobs": {
            "max_attempts": 3,
            "retry_backoff_seconds": [1.0, 2.0],
            "request_timeout_seconds": 10.0,
            "lease_seconds": 12.0,
            "poll_seconds": 0.5,
        },
        "admission": {"wait_timeout_seconds": 15.0},
    }


def test_valid_policy_round_trips_with_global_alias_and_stable_hash() -> None:
    policy = MemoryProductionPolicy.model_validate(policy_data())
    encoded = policy.model_dump_json(by_alias=True)
    restored = MemoryProductionPolicy.model_validate_json(encoded)
    canonical = json.dumps(
        policy.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":")
    )

    assert "global" in policy.model_dump(by_alias=True)
    assert "global_" not in policy.model_dump(by_alias=True)
    assert restored == policy
    assert policy.policy_hash() == hashlib.sha256(canonical.encode()).hexdigest()
    assert restored.policy_hash() == policy.policy_hash()


def test_policy_and_nested_sequences_are_immutable() -> None:
    policy = MemoryProductionPolicy.model_validate(policy_data())

    with pytest.raises(ValidationError):
        policy.raw_turns = 9
    with pytest.raises((AttributeError, TypeError, ValidationError)):
        policy.facts.importance_levels[0].name = "changed"
    with pytest.raises((AttributeError, TypeError)):
        policy.jobs.retry_backoff_seconds[0] = 4.0


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("raw_turns", -1),
        ("batch_turns", 0),
        ("intermediate_limit", -1),
        ("backlog_batches", -1),
        ("facts.max_per_batch", -1),
        ("global.target_words", 0),
        ("jobs.max_attempts", 0),
        ("jobs.request_timeout_seconds", 0.0),
        ("jobs.lease_seconds", 0.0),
        ("jobs.poll_seconds", 0.0),
        ("admission.wait_timeout_seconds", 0.0),
    ],
)
def test_rejects_out_of_range_values(path: str, value: object) -> None:
    data = policy_data()
    target = data
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]  # type: ignore[assignment]
    target[parts[-1]] = value

    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate(data)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("raw_turns", True),
        ("batch_turns", "4"),
        ("facts.max_per_batch", 3.0),
        ("global.target_words", "500"),
        ("jobs.max_attempts", True),
        ("jobs.request_timeout_seconds", "10"),
    ],
)
def test_rejects_coercive_values(path: str, value: object) -> None:
    data = policy_data()
    target = data
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]  # type: ignore[assignment]
    target[parts[-1]] = value

    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate(data)


@pytest.mark.parametrize("backoff", [[1.0], [1.0, 2.0, 3.0], [1.0, float("inf")]])
def test_retry_backoff_must_be_finite_and_match_attempt_count(backoff: list[float]) -> None:
    data = policy_data()
    data["jobs"]["retry_backoff_seconds"] = backoff  # type: ignore[index]

    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate(data)


@pytest.mark.parametrize("seconds", [float("inf"), float("nan"), -0.1])
def test_duration_values_must_be_finite_and_nonnegative(seconds: float) -> None:
    data = policy_data()
    data["jobs"]["retry_backoff_seconds"] = [seconds, 2.0]  # type: ignore[index]

    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate(data)


def test_lease_must_cover_request_timeout() -> None:
    data = policy_data()
    data["jobs"]["lease_seconds"] = 10.0  # type: ignore[index]

    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate(data)


def test_requires_all_values_and_has_no_numeric_defaults() -> None:
    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate({})

    assert all(field.is_required() for field in MemoryProductionPolicy.model_fields.values())


def test_rejects_extra_fields_at_every_level() -> None:
    data = policy_data()
    data["unexpected"] = True
    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate(data)

    data = policy_data()
    data["facts"]["unexpected"] = True  # type: ignore[index]
    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate(data)


@pytest.mark.parametrize(
    "levels",
    [
        [],
        [
            {"name": "same", "criteria": "Relevant", "examples": "Clue"},
            {"name": "same", "criteria": "Major", "examples": "Betrayal"},
        ],
    ],
)
def test_importance_levels_must_be_nonempty_and_unique(levels: list[dict[str, str]]) -> None:
    data = policy_data()
    data["facts"]["importance_levels"] = levels  # type: ignore[index]

    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate(data)


def test_accepts_one_importance_level_without_assumed_names() -> None:
    data = policy_data()
    data["facts"]["importance_levels"] = [  # type: ignore[index]
        {"name": "custom", "criteria": "Relevant", "examples": "Clue"}
    ]

    policy = MemoryProductionPolicy.model_validate(data)

    assert [level.name for level in policy.facts.importance_levels] == ["custom"]


@pytest.mark.parametrize("field", ["name", "criteria", "examples"])
@pytest.mark.parametrize("value", ["", " \t\n "])
def test_rejects_empty_or_whitespace_importance_text(field: str, value: str) -> None:
    data = policy_data()
    data["facts"]["importance_levels"][0][field] = value  # type: ignore[index]

    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate(data)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("jobs.request_timeout_seconds", True),
        ("jobs.retry_backoff_seconds", [True, 2.0]),
    ],
)
def test_rejects_boolean_float_values(path: str, value: object) -> None:
    data = policy_data()
    parts = path.split(".")
    target = data
    for part in parts[:-1]:
        target = target[part]  # type: ignore[assignment]
    if parts[-1] == "retry_backoff_seconds":
        target[parts[-1]] = value  # type: ignore[index]
    else:
        target[parts[-1]] = value

    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate(data)


def test_rejects_provider_and_model_settings() -> None:
    data = policy_data()
    data["provider"] = "openai"
    data["model"] = "example"

    with pytest.raises(ValidationError):
        MemoryProductionPolicy.model_validate(data)
