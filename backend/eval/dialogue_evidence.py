import json
from dataclasses import asdict
from pathlib import Path

from dialogue_cases import CASES
from dialogue_plan import trial_key
from ledger import RequestLedger
from usage_report import usage_csv, usage_markdown


def json_default(value: object) -> object:
    if isinstance(value, frozenset | set):
        return sorted(value)
    raise TypeError("Evaluation evidence contains a non-JSON value.")


def read_evidence(path: Path) -> tuple[dict[str, dict], set[str]]:
    completed: dict[str, dict] = {}
    latest: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            latest[row["key"]] = row["event"]
            if row["event"] == "result":
                completed[row["key"]] = row
    return completed, {key for key, event in latest.items() if event == "started"}


def append_evidence(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=json_default) + "\n")


def write_inventory(
    path: Path,
    plan: dict,
    completed: dict[str, dict],
    ledger: RequestLedger,
    timing: dict | None = None,
) -> None:
    pending = [
        {"case": case.name, "model": model, "run": run}
        for run in range(plan["runs_per_model_case"])
        for case in (next(c for c in CASES if c.name == name) for name in plan["cases"])
        for model in plan["models"]
        if trial_key(plan, case.name, model, run) not in completed
        or completed[trial_key(plan, case.name, model, run)].get("retryable")
        or completed[trial_key(plan, case.name, model, run)].get("trial_status")
        in {"request_budget_stopped", "provider_paused"}
    ]
    result = {
        "suite": plan["suite"],
        "source_hash": plan["source_hash"],
        "recorded_trials": len(completed),
        "target_trials": plan["trials"],
        "all_trials_recorded": not pending,
        "acceptance": "pending complete-suite owner review",
        "daily_spent": ledger.spent,
        "daily_remaining": ledger.remaining,
        "pending": pending,
        "retryable": [
            {"case": row["case"], "model": row["model"], "run": row["run"]}
            for row in completed.values()
            if row.get("retryable")
        ],
        "timing": timing or {},
    }
    path.with_suffix(".summary.json").write_text(json.dumps(result, indent=2))
    ledger_paths = {ledger.path.resolve()}
    ledger_paths.update(
        Path(row["ledger"]).resolve() for row in completed.values() if row.get("ledger")
    )
    if path.exists():
        for text in path.read_text().splitlines():
            row = json.loads(text)
            if row.get("ledger"):
                ledger_paths.add(Path(row["ledger"]).resolve())
    rows = [
        {**asdict(attempt), "ledger": str(ledger_path)}
        for ledger_path in sorted(ledger_paths)
        if ledger_path.exists()
        for attempt in RequestLedger(ledger_path).results()
    ]
    path.with_suffix(".usage.csv").write_text(usage_csv(rows), encoding="utf-8")
    path.with_suffix(".usage.md").write_text(usage_markdown(rows), encoding="utf-8")
    print(
        f"Recorded {len(completed)}/{plan['trials']} trials; daily requests {ledger.spent}/{ledger.budget}."
    )
    print(f"Retryable failures: {len(result['retryable'])}.")
    print("No acceptance judgment is made by this runner.")
