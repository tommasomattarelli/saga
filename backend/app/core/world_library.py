"""ADR 0008 — game home + world library (C9, D4, I5b).

The library lives in `<SAGA_HOME>/worlds` (default `~/.saga/worlds`), is
created lazily, seeded with the bundled example World when empty, and
initialized as a git repository with a repo-local identity. Git failures
never block read paths — only editor saves require git (I6).
"""

import os
import shutil
import subprocess
from pathlib import Path

import structlog
import yaml

from app.config_loader import load_saga_config

logger = structlog.get_logger()

# Docker mounts bundled worlds at /worlds; locally they live at <repo>/worlds.
_REPO_WORLDS = Path(__file__).resolve().parents[3] / "worlds"


def saga_home() -> Path:
    env = os.getenv("SAGA_HOME")
    if env:
        return Path(env)
    configured = (load_saga_config().get("world") or {}).get("home")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".saga"


def worlds_dir() -> Path:
    return saga_home() / "worlds"


def bundled_worlds_dir() -> Path:
    docker_mount = Path("/worlds")
    return docker_mount if docker_mount.is_dir() else _REPO_WORLDS


def _git(worlds: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(worlds), *args],
        check=True,
        capture_output=True,
        timeout=30,
    )


def _init_git(worlds: Path) -> None:
    if (worlds / ".git").is_dir():
        return
    try:
        _git(worlds, "init")
        _git(worlds, "config", "user.name", "SAGA World Editor")
        _git(worlds, "config", "user.email", "saga@localhost")
        _git(worlds, "add", "-A")
        _git(worlds, "commit", "-m", "library: initial state", "--allow-empty")
    except (OSError, subprocess.SubprocessError) as exc:
        # Read paths never need git; only editor saves do (I6) — warn and go on.
        logger.warning("world_library_git_init_failed", error=str(exc))


def ensure_library() -> Path:
    worlds = worlds_dir()
    worlds.mkdir(parents=True, exist_ok=True)
    if not any(p.is_dir() for p in worlds.iterdir()):
        bundled = bundled_worlds_dir()
        if bundled.is_dir():
            for world in bundled.iterdir():
                if world.is_dir() and (world / "world.yaml").is_file():
                    shutil.copytree(world, worlds / world.name)
    _init_git(worlds)
    return worlds


def world_path(slug: str) -> Path | None:
    candidate = worlds_dir() / slug
    return candidate if (candidate / "world.yaml").is_file() else None


def list_worlds() -> list[dict]:
    cards: list[dict] = []
    if not worlds_dir().is_dir():
        return cards
    for world in sorted(worlds_dir().iterdir()):
        manifest = world / "world.yaml"
        if not manifest.is_file():
            continue
        try:
            meta = (yaml.safe_load(manifest.read_text()) or {}).get("meta", {})
        except yaml.YAMLError:
            logger.warning("world_library_unreadable_world", world=world.name)
            continue
        cards.append(
            {
                "slug": world.name,
                "name": meta.get("name", world.name),
                "description": meta.get("description", ""),
                "author": meta.get("author", ""),
                "version": meta.get("version", ""),
                "tags": meta.get("tags", []),
            }
        )
    return cards
