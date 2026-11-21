from __future__ import annotations

import hashlib
import json
from pathlib import Path

_fingerprints: dict[Path, tuple[object, str]] = {}


def digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def implementation_fingerprint(root: Path) -> str:
    paths = list((root / "app").rglob("*.py")) + list((root / "eval").rglob("*.py"))
    paths += list((root / "app" / "ai" / "prompts").rglob("*.yaml"))
    paths += list((root.parent / "worlds" / "the-awakening").rglob("*.yaml"))
    paths += [
        path
        for path in (root.parent / "saga.config.yaml", root / "pyproject.toml", root / "uv.lock")
        if path.is_file()
    ]
    paths = sorted(set(paths))
    signature = (
        Path.read_bytes,
        tuple(
            (str(path), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
            for path, stat in ((path, path.stat()) for path in paths)
        ),
    )
    cached = _fingerprints.get(root)
    if cached is not None and cached[0] == signature:
        return cached[1]
    value = digest(
        {
            str(path.relative_to(root.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        }
    )
    _fingerprints[root] = signature, value
    return value
