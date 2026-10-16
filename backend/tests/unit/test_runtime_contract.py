import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_python_runtime_contract() -> None:
    backend = ROOT / "backend"
    version = (backend / ".python-version").read_text().strip()
    project = tomllib.loads((backend / "pyproject.toml").read_text())
    lock = tomllib.loads((backend / "uv.lock").read_text())

    assert re.fullmatch(r"3\.12\.\d+", version)
    assert project["project"]["requires-python"] == ">=3.12,<3.13"
    assert lock["requires-python"] == "==3.12.*"


def test_node_runtime_contract() -> None:
    frontend = ROOT / "frontend"
    version = (frontend / ".node-version").read_text().strip()
    package = json.loads((frontend / "package.json").read_text())
    lock = json.loads((frontend / "package-lock.json").read_text())

    assert re.fullmatch(r"24\.\d+\.\d+", version)
    assert package["engines"]["node"] == ">=24.0.0 <25"
    assert lock["packages"][""]["engines"] == package["engines"]
    assert (frontend / ".npmrc").read_text().strip() == "engine-strict=true"


@pytest.mark.parametrize(
    ("directory", "pin", "image"),
    [
        ("backend", ".python-version", "python:{version}-slim"),
        ("frontend", ".node-version", "node:{version}-alpine"),
    ],
)
def test_docker_matches_runtime_pin(directory: str, pin: str, image: str) -> None:
    path = ROOT / directory
    version = (path / pin).read_text().strip()
    dockerfile = (path / "Dockerfile").read_text()

    assert dockerfile.splitlines()[0] == f"FROM {image.format(version=version)}"
    assert pin in dockerfile


def test_ci_matches_runtime_pins() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    python_version = (ROOT / "backend/.python-version").read_text().strip()
    versions = re.findall(r'python-version: "([^"]+)"', workflow)

    assert len(versions) == 3
    assert set(versions) == {python_version}
    assert "node-version-file: frontend/.node-version" in workflow


@pytest.mark.parametrize(
    "path",
    [
        "backend/Dockerfile",
        "install/linux-macos/install_saga.sh",
        "install/windows/install_saga.ps1",
    ],
)
def test_installations_cannot_update_python_lock(path: str) -> None:
    assert "uv sync --locked --no-dev" in (ROOT / path).read_text()


@pytest.mark.parametrize(
    "path",
    [
        "docker-compose.yml",
        "install/linux-macos/start_saga.sh",
        "install/windows/start_saga.ps1",
    ],
)
def test_launchers_preserve_production_dependencies(path: str) -> None:
    assert "uv run --locked --no-dev uvicorn" in (ROOT / path).read_text()


def test_docker_default_preserves_production_dependencies() -> None:
    dockerfile = (ROOT / "backend/Dockerfile").read_text()

    assert '["uv", "run", "--locked", "--no-dev", "uvicorn"' in dockerfile


def test_ci_cannot_update_python_lock() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    commands = re.findall(r"uv (?:sync|run)[^\n]*", workflow)

    assert commands
    assert all("--locked" in command for command in commands)


def test_installer_smoke_preserves_production_dependencies() -> None:
    workflow = (ROOT / ".github/workflows/installer-smoke.yml").read_text()

    assert "'run','--locked','--no-dev','uvicorn'" in workflow
    assert workflow.count("uv run --locked --no-dev uvicorn") == 2


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        "frontend/Dockerfile",
        "install/linux-macos/install_saga.sh",
        "install/windows/install_saga.ps1",
    ],
)
def test_frontend_installation_uses_standard_peer_resolution(path: str) -> None:
    source = (ROOT / path).read_text()

    assert "npm ci" in source
    assert "--legacy-peer-deps" not in source
