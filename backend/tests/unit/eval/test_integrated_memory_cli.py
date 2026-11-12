import json

import pytest

from tests.unit.eval._integrated_sources import integrated_source


def test_integrated_prepare_validate_report_are_offline(tmp_path, monkeypatch) -> None:
    from eval.integrated_memory.cli import main as integrated_main

    source_path = tmp_path / "sources.json"
    output = tmp_path / "integrated"
    source_path.write_text(json.dumps(integrated_source(12)))
    monkeypatch.setattr(
        "sys.argv",
        [
            "integrated-memory",
            "prepare",
            "--sources",
            str(source_path),
            "--output",
            str(output),
            "--run-id",
            "offline-cli",
            "--embedding-max-retries",
            "1",
        ],
    )
    integrated_main()
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["approved"] is False
    assert manifest["embedding_policy"]["max_retries"] == 1
    assert manifest["executable"] is False
    monkeypatch.setattr("sys.argv", ["integrated-memory", "validate", "--output", str(output)])
    integrated_main()
    monkeypatch.setattr("sys.argv", ["integrated-memory", "report", "--output", str(output)])
    integrated_main()
    assert "Separate per-run authorization is required" in (output / "report.md").read_text()
    assert not (output / "requests.jsonl").exists()


def test_integrated_run_requires_authorization_before_runner_import(tmp_path, monkeypatch) -> None:
    from eval.integrated_memory.cli import main as integrated_main

    monkeypatch.setattr(
        "sys.argv",
        [
            "integrated-memory",
            "run",
            "--output",
            str(tmp_path),
            "--user",
            "00000000-0000-0000-0000-000000000001",
        ],
    )
    with pytest.raises(SystemExit) as stopped:
        integrated_main()
    assert stopped.value.code == 2
