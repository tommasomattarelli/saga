import pytest

from app.core.action_policy import ActionPolicy, get_action_policy


def test_action_policy_derives_finite_deadlines(monkeypatch):
    monkeypatch.setattr(
        "app.core.action_policy.load_saga_config",
        lambda: {
            "gameplay": {
                "action_timeout_seconds": 600,
                "action_completion_margin_seconds": 50,
                "action_proxy_margin_seconds": 80,
            },
            "memory": {"production": {"admission": {"wait_timeout_seconds": 10}}},
        },
    )

    policy = get_action_policy()

    assert policy.execution_lease_seconds == 650
    assert policy.client_timeout_seconds == 650
    assert policy.proxy_timeout_seconds == 680


@pytest.mark.parametrize(
    ("completion_margin", "admission_wait"),
    [(10, 10), (9, 10), (float("inf"), 1)],
)
def test_action_policy_rejects_unsafe_or_nonfinite_margins(completion_margin, admission_wait):
    with pytest.raises(ValueError):
        ActionPolicy.model_validate(
            {
                **get_action_config(),
                "admission_wait_seconds": admission_wait,
            }
        )


def test_action_policy_rejects_proxy_margin_not_above_completion_margin():
    with pytest.raises(ValueError):
        ActionPolicy.model_validate(
            {
                "timeout_seconds": 600,
                "completion_margin_seconds": 50,
                "proxy_margin_seconds": 50,
                "admission_wait_seconds": 10,
            }
        )


def get_action_config() -> dict[str, int]:
    return {
        "action_timeout_seconds": 60,
        "action_completion_margin_seconds": 15,
        "action_proxy_margin_seconds": 20,
    }


def test_action_policy_loader_exposes_yaml_values(monkeypatch):
    monkeypatch.setattr(
        "app.core.action_policy.load_saga_config",
        lambda: {
            "gameplay": get_action_config(),
            "memory": {"production": {"admission": {"wait_timeout_seconds": 10}}},
        },
    )

    assert get_action_policy().timeout_seconds == 60
