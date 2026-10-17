from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("hook", ["ruff", "ruff-format"])
def test_ruff_hooks_use_backend_configuration(hook: str) -> None:
    config = (ROOT / ".pre-commit-config.yaml").read_text()
    block = config.split(f"      - id: {hook}\n", 1)[1]
    block = block.split("\n      - id:", 1)[0].split("\n  - repo:", 1)[0]

    assert "--config" in block
    assert "backend/pyproject.toml" in block


def test_windows_make_uses_process_scoped_execution_policy() -> None:
    config = (ROOT / "Makefile").read_text()
    windows = config.split("ifeq ($(OS),Windows_NT)", 1)[1].split("\nelse\n", 1)[0]

    assert ".SHELLFLAGS := -NoProfile -ExecutionPolicy Bypass -Command" in windows
