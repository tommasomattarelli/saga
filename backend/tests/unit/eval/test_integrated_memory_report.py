from tests.unit.eval._integrated_sources import integrated_source


def test_integrated_report_marks_code_drift_and_excludes_player_generation(tmp_path) -> None:
    from eval.integrated_memory.plan import prepare_plan as prepare_integrated_plan
    from eval.integrated_memory.plan import write_plan as write_integrated_plan
    from eval.integrated_memory.report import write_report as write_integrated_report

    source = integrated_source()
    plan = prepare_integrated_plan(sources=source, run_id="report-drift")
    write_integrated_plan(plan, tmp_path)
    write_integrated_report(tmp_path)
    report = (tmp_path / "report.md").read_text()
    assert "31 requests" in report and "42" in report
    assert "66" in report and "submitted-text attempt cap" in report
    assert "implementation drift: no" in report
    assert "DM generation, NPC generation, recall and probes are excluded" in report


def test_integrated_report_remains_readable_after_code_drift(tmp_path, monkeypatch) -> None:
    import eval.integrated_memory.report as integrated_report
    from eval.integrated_memory.plan import prepare_plan as prepare_integrated_plan
    from eval.integrated_memory.plan import write_plan as write_integrated_plan
    from eval.integrated_memory.report import write_report as write_integrated_report

    plan = prepare_integrated_plan(sources=integrated_source(), run_id="drift-readable")
    write_integrated_plan(plan, tmp_path)
    monkeypatch.setattr(integrated_report, "_fingerprint", lambda root: "changed")
    write_integrated_report(tmp_path)
    assert "implementation drift: yes" in (tmp_path / "report.md").read_text()


def test_integrated_report_reads_saved_run_and_campaign_without_acceptance_claim(tmp_path) -> None:
    import json

    from eval.integrated_memory.plan import prepare_plan as prepare_integrated_plan
    from eval.integrated_memory.plan import write_plan as write_integrated_plan
    from eval.integrated_memory.report import write_report as write_integrated_report

    plan = prepare_integrated_plan(sources=integrated_source(), run_id="saved-evidence")
    write_integrated_plan(plan, tmp_path)
    (tmp_path / "run.json").write_text(
        json.dumps({"state": "completed", "manifest_seal": plan.seal, "campaign_id": "id"})
    )
    (tmp_path / "campaign.json").write_text("{}")
    write_integrated_report(tmp_path)
    report = (tmp_path / "report.md").read_text()
    assert "Run state: completed" in report
    assert "Campaign archive present: true" in report
    assert "does not provide a quality acceptance verdict" in report
