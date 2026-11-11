import sys
from pathlib import Path
from uuid import uuid4

import pytest
from scripts.validate_campaign_export import main

from tests.unit.services.test_export_validation import empty_archive


def test_offline_validator_accepts_a_valid_archive(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / "campaign.json"
    path.write_text(empty_archive().model_dump_json())
    monkeypatch.setattr(sys, "argv", ["validate_campaign_export", str(path)])
    assert main() == 0
    output = capsys.readouterr()
    assert output.out.strip() == "Campaign archive is valid." and output.err == ""


@pytest.mark.parametrize(
    "contents",
    [
        '{"private":"sk-private-secret"',
        '{"format_version":2}',
    ],
)
def test_offline_validator_rejects_bad_json_without_echoing_data(
    tmp_path,
    monkeypatch,
    capsys,
    contents: str,
) -> None:
    path = tmp_path / "campaign.json"
    path.write_text(contents)
    monkeypatch.setattr(sys, "argv", ["validate_campaign_export", str(path)])
    assert main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "invalid" in output.err and "sk-private-secret" not in output.err


def test_offline_validator_rejects_missing_references(tmp_path, monkeypatch, capsys) -> None:
    archive = empty_archive()
    archive.campaign.active_head_turn_id = uuid4()
    path = tmp_path / "campaign.json"
    path.write_text(archive.model_dump_json())
    monkeypatch.setattr(sys, "argv", ["validate_campaign_export", str(path)])
    assert main() == 1
    assert "inconsistent references" in capsys.readouterr().err


def test_offline_validator_reports_unreadable_file(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["validate_campaign_export", str(tmp_path / "missing.json")])
    assert main() == 1
    assert capsys.readouterr().err.strip() == "Campaign archive could not be read."
