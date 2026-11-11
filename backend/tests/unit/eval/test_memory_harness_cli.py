import json

import pytest
from eval.memory.cli import main

from tests.unit.eval.test_memory_harness_plan import fixture_source, policy


def test_dry_run_only_writes_offline_manifest(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_path = tmp_path / "sources.json"
    facts_path = tmp_path / "facts.json"
    output_path = tmp_path / "evidence"
    source_path.write_text(json.dumps([fixture_source()]))
    facts_path.write_text(json.dumps(policy()))
    monkeypatch.setattr(
        "sys.argv",
        [
            "memory-eval",
            "--dry-run",
            "--sources",
            str(source_path),
            "--facts-policy",
            str(facts_path),
            "--language",
            "en",
            "--session-scope",
            "offline-test",
            "--model",
            "provider/model",
            "--repetitions",
            "1",
            "--global-count",
            "0",
            "--output",
            str(output_path),
        ],
    )
    main()
    assert (output_path / "manifest.json").is_file()
    assert (output_path / "report.md").is_file()
    assert not (output_path / "requests.jsonl").exists()


def test_integrated_prepare_validate_report_are_offline(tmp_path, monkeypatch) -> None:
    from eval.integrated_memory.cli import main as integrated_main

    source_path = tmp_path / "sources.json"
    output = tmp_path / "integrated"
    source = fixture_source()
    source["turns"] = [
        {
            "reference": f"t{index}",
            "turn_id": f"00000000-0000-0000-0000-{index:012d}",
            "player_action": "Act",
            "narration": "Result",
            "operations": None,
        }
        for index in range(1, 13)
    ]
    source_path.write_text(json.dumps(source))
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
        ],
    )
    integrated_main()
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["approved"] is False
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
    with pytest.raises(SystemExit):
        integrated_main()
