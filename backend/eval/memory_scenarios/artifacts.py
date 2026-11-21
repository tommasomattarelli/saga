import json
from pathlib import Path

from eval.memory_scenarios.contracts import BuiltScenario


def write_scenario(result: BuiltScenario, out: Path) -> None:
    if out.exists():
        raise FileExistsError(f"output directory already exists: {out}")
    out.mkdir(parents=True)
    (out / "sources.json").write_text(result.sources.canonical_json() + "\n", encoding="utf-8")
    (out / "annotations.json").write_text(
        json.dumps(result.annotations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "batches.json").write_text(
        json.dumps(
            [batch.model_dump(mode="json") for batch in result.batches],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    batch_dir = out / "batches"
    batch_dir.mkdir()
    for index, batch in enumerate(result.batches, start=1):
        (batch_dir / f"batch-{index:03}.json").write_text(
            batch.canonical_json() + "\n", encoding="utf-8"
        )
    if result.tail is not None:
        (out / "incomplete-tail.json").write_text(
            result.tail.canonical_json() + "\n", encoding="utf-8"
        )
    if result.plan is not None:
        (out / "plan.json").write_text(json.dumps(result.plan, indent=2) + "\n", encoding="utf-8")
