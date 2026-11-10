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
