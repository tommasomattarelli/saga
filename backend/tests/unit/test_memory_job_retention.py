from unittest.mock import patch

import pytest

from app.ai.router import get_memory_terminal_payload_retention_days


@pytest.mark.parametrize("value", [True, 1.0, "2", 0, -1])
def test_memory_terminal_retention_requires_positive_integer(value: object) -> None:
    with (
        patch(
            "app.ai.router._load_config",
            return_value={"memory": {"terminal_payload_retention_days": value}},
        ),
        pytest.raises(ValueError, match="terminal_payload_retention_days"),
    ):
        get_memory_terminal_payload_retention_days()


def test_memory_terminal_retention_uses_one_day_default() -> None:
    with patch("app.ai.router._load_config", return_value={}):
        assert get_memory_terminal_payload_retention_days() == 1
