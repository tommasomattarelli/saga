"""World service — editor operations on the library (ADR 0008 I6/I7/C10).

Save flow (I6): serialize to a temp dir → three-tier validation → sync into
the library → git commit. Any failure after the write is rolled back with
git; the library never holds an invalid world.
"""

import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import structlog
from fastapi import HTTPException, status

from app.config_loader import load_saga_config
from app.core.world_library import ensure_library, world_path, worlds_dir
from app.core.world_loader import WorldLoadError, load_world
from app.core.world_validator import validate_world
from app.core.world_writer import to_editable, write_world

logger = structlog.get_logger()


def _max_depth() -> int:
    return int((load_saga_config().get("world") or {}).get("max_depth", 8))


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="World name must contain at least one letter or digit",
        )
    return slug


def _git_commit(message: str) -> None:
    worlds = worlds_dir()
    try:
        subprocess.run(
            ["git", "-C", str(worlds), "add", "-A"], check=True, capture_output=True, timeout=30
        )
        subprocess.run(
            ["git", "-C", str(worlds), "commit", "-m", message, "--allow-empty"],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Saving requires git in the world library and it failed — the change was kept on disk but not committed.",
        ) from exc


def _git_rollback() -> None:
    worlds = worlds_dir()
    try:
        subprocess.run(
            ["git", "-C", str(worlds), "checkout", "--", "."],
            check=True,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            ["git", "-C", str(worlds), "clean", "-fd"], check=True, capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        logger.error("world_library_rollback_failed")


def _validate_dir(world_dir: Path, slug: str) -> None:
    try:
        asset = load_world(world_dir)
    except WorldLoadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"World '{slug}' failed to load: {exc}",
        ) from exc
    errors = validate_world(asset, max_depth=_max_depth())
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": f"World '{slug}' is invalid", "errors": errors[:20]},
        )


def _card(slug: str) -> dict:
    asset = load_world(worlds_dir() / slug)
    return {
        "slug": slug,
        "name": asset.meta.name,
        "description": asset.meta.description,
        "author": asset.meta.author,
        "version": asset.meta.version,
        "tags": asset.meta.tags,
    }


def get_editable_world(slug: str) -> dict:
    ensure_library()
    path = world_path(slug)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"World '{slug}' not found"
        )
    return {"slug": slug, **to_editable(load_world(path))}


def create_world(meta: dict) -> dict:
    ensure_library()
    slug = _slugify(meta.get("name", ""))
    if (worlds_dir() / slug).exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A world named '{slug}' already exists — pick another name",
        )
    # The wizard starts from the bundled default taxonomy (I7).
    example = load_world(worlds_dir() / "the-awakening") if world_path("the-awakening") else None
    taxonomy = (
        example.taxonomy.model_dump(mode="json")
        if example
        else {"kinds": [{"name": "place", "scale": "outdoor"}]}
    )
    payload: dict = {
        "meta": {
            "name": meta.get("name", slug),
            "author": meta.get("author", ""),
            "version": "1.0.0",
            "description": meta.get("description", ""),
            "tags": meta.get("tags", []),
        },
        "root": {"kind": taxonomy["kinds"][0]["name"], "description": meta.get("description", "")},
        "taxonomy": taxonomy,
        "scenario": None,
        "nodes": [],
        "edges": [],
        "factions": [],
        "npcs": [],
        "encounters": [],
    }
    write_world(payload, worlds_dir() / slug)
    try:
        _validate_dir(worlds_dir() / slug, slug)
    except HTTPException:
        shutil.rmtree(worlds_dir() / slug, ignore_errors=True)
        raise
    _git_commit(f"editor: create {slug}")
    return _card(slug)


def save_world(slug: str, payload: dict) -> dict:
    ensure_library()
    target = world_path(slug)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"World '{slug}' not found"
        )

    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / slug
        write_world(payload, staged)
        _validate_dir(staged, slug)
        shutil.rmtree(target)
        shutil.copytree(staged, target)

    try:
        _validate_dir(target, slug)
        _git_commit(f"editor: update {slug}")
    except HTTPException:
        _git_rollback()
        raise
    return _card(slug)


def delete_world(slug: str) -> None:
    ensure_library()
    target = world_path(slug)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"World '{slug}' not found"
        )
    shutil.rmtree(target)
    _git_commit(f"editor: delete {slug}")


def export_world(slug: str) -> bytes:
    ensure_library()
    target = world_path(slug)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"World '{slug}' not found"
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(target.rglob("*")):
            if file.is_file():
                zf.write(file, f"{slug}/{file.relative_to(target)}")
    return buffer.getvalue()


def import_world(data: bytes) -> dict:
    ensure_library()
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The uploaded file is not a valid world zip",
        ) from exc

    with tempfile.TemporaryDirectory() as tmp:
        archive.extractall(tmp)
        candidates = [p for p in Path(tmp).iterdir() if (p / "world.yaml").is_file()]
        if len(candidates) != 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The zip must contain exactly one world directory (with world.yaml at its root)",
            )
        staged = candidates[0]
        slug = staged.name
        if (worlds_dir() / slug).exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A world named '{slug}' already exists — rename the folder inside the zip",
            )
        _validate_dir(staged, slug)
        shutil.copytree(staged, worlds_dir() / slug)

    _git_commit(f"editor: import {slug}")
    return _card(slug)
