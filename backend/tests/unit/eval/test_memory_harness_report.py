import json
from unittest.mock import Mock

from eval.memory.plan import prepare_plan, write_plan
from eval.memory.report import write_report


def test_recovered_ledger_rows_keep_the_regular_numeric_batch_identity() -> None:
    from eval.memory.report import _row_from_attempt
    from eval.support.ledger import Attempt

    row = _row_from_attempt(Attempt("key", "batch-1", "split-facts", 1, status="ok"))
    assert row["batch"] == 1


def test_report_separates_human_review_and_reports_size_without_fake_tokens(tmp_path) -> None:
    source = {
        "turns": [
            {
                "reference": "t1",
                "turn_id": "00000000-0000-0000-0000-000000000001",
                "player_action": "Ask",
                "narration": "秘密",
                "operations": None,
            },
            {
                "reference": "t2",
                "turn_id": "00000000-0000-0000-0000-000000000002",
                "player_action": "Wait",
                "narration": "休む",
                "operations": None,
            },
        ]
    }
    policy = {
        "max_per_batch": 1,
        "importance_levels": [{"name": "high", "criteria": "Major", "examples": "Secret"}],
    }
    plan = prepare_plan(
        sources=[source],
        facts_policy=policy,
        global_policy=None,
        language="ja",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
        session_scope="report-test",
    )
    write_plan(plan, tmp_path)
    (tmp_path / "outputs.jsonl").write_text(
        json.dumps({"arm": "batch", "attempt": 1, "status": "ok", "raw": "秘密"}) + "\n"
    )
    write_report(tmp_path, plan)
    report = (tmp_path / "report.md").read_text()
    assert "6 UTF-8 bytes" in report
    assert "token estimate: unavailable" in report
    assert "Summary quality" in report and "Facts quality" in report
    assert "pass" not in report.lower()
    notes = tmp_path / "owner-notes.md"
    assert "[owner review]" in notes.read_text()
    notes.write_text("owner's unchanged notes\n")
    write_report(tmp_path, plan)
    assert notes.read_text() == "owner's unchanged notes\n"


def test_report_pairs_unified_against_both_split_roles_and_keeps_unknown_usage(tmp_path) -> None:
    source = {
        "turns": [
            {
                "reference": "t1",
                "turn_id": "00000000-0000-0000-0000-000000000001",
                "player_action": "Ask",
                "narration": "A",
                "operations": None,
            },
            {
                "reference": "t2",
                "turn_id": "00000000-0000-0000-0000-000000000002",
                "player_action": "Wait",
                "narration": "B",
                "operations": None,
            },
        ]
    }
    facts_policy = {
        "max_per_batch": 1,
        "importance_levels": [{"name": "high", "criteria": "Major", "examples": "Secret"}],
    }
    plan = prepare_plan(
        sources=[source],
        facts_policy=facts_policy,
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
        session_scope="report-test",
    )
    rows = [
        {
            "model": "provider/model",
            "repetition": 1,
            "batch": 1,
            "mode": "unified",
            "status": "ok",
            "raw": "x",
            "provider": "openrouter",
            "seconds": 1.0,
            "usage": [{"cost": 1.0, "currency": "USD", "input_tokens": None}],
        },
        {
            "model": "provider/model",
            "repetition": 1,
            "batch": 1,
            "mode": "split-summary",
            "status": "ok",
            "raw": "y",
            "provider": "openrouter",
            "seconds": 2.0,
            "usage": [{"cost": 0.3, "currency": "USD"}],
        },
        {
            "model": "provider/model",
            "repetition": 1,
            "batch": 1,
            "mode": "split-facts",
            "status": "error",
            "raw": "bad",
            "provider": "openrouter",
            "seconds": 3.0,
            "usage": [{"cost": 0.2, "currency": "USD"}],
        },
    ]
    (tmp_path / "outputs.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    write_report(tmp_path, plan)
    report = (tmp_path / "report.md").read_text()
    assert "invalid/incomplete" in report
    assert "1.0 USD" in report and "0.5 USD" in report
    assert "unknown" in report


def test_report_cli_uses_saved_sizes_without_current_code_or_provider_lookup(
    tmp_path, monkeypatch
) -> None:
    import eval.memory.plan as plan_module
    from eval.memory.report import main

    source = {
        "turns": [
            {
                "reference": "t1",
                "turn_id": "00000000-0000-0000-0000-000000000001",
                "player_action": "Ask",
                "narration": "A",
                "operations": None,
            },
            {
                "reference": "t2",
                "turn_id": "00000000-0000-0000-0000-000000000002",
                "player_action": "Wait",
                "narration": "B",
                "operations": None,
            },
        ]
    }
    facts_policy = {
        "max_per_batch": 1,
        "importance_levels": [{"name": "high", "criteria": "Major", "examples": "Secret"}],
    }
    plan = prepare_plan(
        sources=[source],
        facts_policy=facts_policy,
        global_policy={"target_words": 100},
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=1,
        session_scope="report-test",
    )
    write_plan(plan, tmp_path)
    monkeypatch.setattr("sys.argv", ["eval.memory.report", "--output", str(tmp_path)])
    monkeypatch.setattr(plan_module, "current_implementation_fingerprint", lambda: "changed")
    monkeypatch.setattr(plan_module, "get_instance_default", Mock(side_effect=AssertionError))
    main()
    report = (tmp_path / "report.md").read_text()
    assert "initial only; successor input unknown until produced" in report
    assert "Request JSON UTF-8 bytes" in report
