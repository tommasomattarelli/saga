import json
from pathlib import Path

import pytest

from app.migrations import profiles
from app.migrations.errors import MigrationConfigurationError


def test_load_profile_rejects_invalid_catalog_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = profiles.PROFILE_DIR / "current_post_pr1.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    del payload["schema"]["tables"]["public.users"]["columns"]["username"]["collation"]
    (tmp_path / source.name).write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(profiles, "PROFILE_DIR", tmp_path)

    with pytest.raises(MigrationConfigurationError, match="profile .* is invalid"):
        profiles.load_profile("current_post_pr1")


def test_load_profile_rejects_unhashable_catalog_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = profiles.PROFILE_DIR / "current_post_pr1.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["schema"]["relations"]["public.users"] = []
    (tmp_path / source.name).write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(profiles, "PROFILE_DIR", tmp_path)

    with pytest.raises(MigrationConfigurationError, match="profile .* is invalid"):
        profiles.load_profile("current_post_pr1")
