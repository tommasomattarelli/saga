from uuid import uuid4

from eval.memory.plan import prepare_plan
from eval.memory.report import write_report
from eval.support.ledger import Attempt, RequestLedger

from tests.unit.eval.test_memory_harness_plan import fixture_source, policy


def test_report_exposes_stable_per_model_session_headers(tmp_path) -> None:
    plan = prepare_plan(
        sources=[fixture_source()],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["vendor/one", "vendor/two"],
        repetitions=1,
        global_count=0,
        session_scope="shared-memory-evaluation",
    )
    ledger = RequestLedger(tmp_path / "requests.jsonl")
    for model in plan.models:
        attempt = Attempt(
            key=str(uuid4()),
            scenario="batch-1",
            probe="unified",
            run=1,
            model=model,
            status="ok",
            request_headers={"x-session-id": plan.model_session_id(model)},
        )
        ledger.reserve(attempt)
        ledger.record(attempt)
    write_report(tmp_path, plan)
    report = (tmp_path / "report.md").read_text()
    assert "shared-memory-evaluation" in report
    assert "x-session-id" in report
    assert all(plan.model_session_id(model) in report for model in plan.models)
    assert "does not guarantee cache hits" in report
