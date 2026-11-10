from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from eval.memory.plan import MemoryPlan, load_saved_plan
from eval.support.ledger import Attempt, RequestLedger


def _size(text: str) -> str:
    return f"{len(text)} characters; {len(text.encode('utf-8'))} UTF-8 bytes; token estimate: unavailable"


def _cell(value: object) -> str:
    if value is None:
        return "unknown"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _rows(directory: Path, ledger: RequestLedger) -> list[dict[str, object]]:
    output_path = directory / "outputs.jsonl"
    rows = (
        [
            json.loads(line)
            for line in output_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if output_path.exists()
        else []
    )
    keys = {str(row.get("key", "")) for row in rows}
    for attempt in ledger.results():
        if attempt.key not in keys:
            rows.append(_row_from_attempt(attempt))
    return rows


def _row_from_attempt(attempt: Attempt) -> dict[str, object]:
    response = attempt.response
    return {
        "key": attempt.key,
        "model": attempt.model,
        "provider": attempt.correlation.get("provider"),
        "repetition": attempt.run,
        "batch": int(attempt.scenario.removeprefix("batch-")),
        "mode": attempt.probe,
        "status": attempt.status,
        "seconds": attempt.seconds,
        "usage": attempt.usage,
        "raw": response.get("raw", ""),
        "payload": response.get("payload"),
        "facts": response.get("facts", []),
        "error": attempt.error,
    }


def _number(value: object) -> str:
    return "unknown" if value is None else str(value)


def _split_outcome(group: dict[str, dict[str, object]]) -> str:
    summary = group.get("split-summary")
    facts = group.get("split-facts")
    return (
        "contract-valid"
        if summary and facts and summary.get("status") == facts.get("status") == "ok"
        else "invalid/incomplete"
    )


def _write_owner_notes(directory: Path) -> None:
    path = directory / "owner-notes.md"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(
                "# Owner review\n\n"
                "## Summary quality\n\n[owner review]\n\n"
                "## Facts quality\n\n[owner review]\n\n"
                "## Global quality\n\n[owner review]\n\n"
                "## Pair comparison\n\n[owner review]\n"
            )
    except FileExistsError:
        pass


def write_report(directory: Path, plan: MemoryPlan) -> None:
    ledger = RequestLedger(directory / "requests.jsonl")
    rows = _rows(directory, ledger)
    lines = [
        "# Memory producer evaluation",
        "",
        f"Models: {', '.join(plan.models)}. Repetitions: {plan.repetitions}. "
        f"Attempts: {ledger.spent}/{plan.call_budget}. Interrupted: {len(ledger.interrupted())}.",
        "",
        "Contract status is not narrative quality; no model judge or tokenizer was used.",
        "Missing provider usage means unknown, not zero.",
        "",
        "## Per-role evidence",
        "",
        "| Model | Rep | Batch | Role | Status | Provider | Seconds | Input | Cached input | Output | Total | Reasoning | Cost | Currency | Output size |",
        "|---|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    lines.extend(
        [
            "",
            "## Prepared input sizes",
            "",
            "Prompt sizes were captured from `prepare_request` with the full schema and rubric. "
            "Request bytes describe the canonical generation-API envelope, not provider wire "
            "format or billed tokens; token estimates are unavailable.",
            "",
            "| Model | Batch | Role | System characters / UTF-8 bytes | User characters / UTF-8 bytes | Request JSON UTF-8 bytes | Note |",
            "|---|---:|---|---:|---:|---:|---|",
        ]
    )
    for prompt_size in plan.input_sizes:
        note = prompt_size.note or ""
        if prompt_size.role == "global":
            note = "initial only; successor input unknown until produced"
        size_cells = (
            prompt_size.model,
            prompt_size.batch,
            prompt_size.role,
            f"{prompt_size.system_characters} / {prompt_size.system_utf8_bytes}",
            f"{prompt_size.user_characters} / {prompt_size.user_utf8_bytes}",
            prompt_size.request_utf8_bytes,
            note,
        )
        lines.append("| " + " | ".join(_cell(value) for value in size_cells) + " |")
    groups: dict[tuple[str, object, object], dict[str, dict[str, object]]] = defaultdict(dict)
    for row in rows:
        usage_values = row.get("usage", [])
        usage = usage_values[0] if isinstance(usage_values, list) and usage_values else {}
        if not isinstance(usage, dict):
            usage = {}
        output_size = _size(str(row.get("raw", "")))
        cells = (
            row.get("model"),
            row.get("repetition"),
            row.get("batch"),
            row.get("mode"),
            row.get("status"),
            row.get("provider"),
            row.get("seconds"),
            _number(usage.get("input_tokens")),
            _number(usage.get("cached_input_tokens")),
            _number(usage.get("output_tokens")),
            _number(usage.get("total_tokens")),
            _number(usage.get("reasoning_output_tokens")),
            _number(usage.get("cost")),
            _number(usage.get("currency")),
            output_size,
        )
        lines.append("| " + " | ".join(_cell(value) for value in cells) + " |")
        if row.get("mode") != "global":
            key = (str(row.get("model", "")), row.get("repetition"), row.get("batch"))
            groups[key][str(row.get("mode", ""))] = row
    lines.extend(
        [
            "",
            "## Unified versus split contract status",
            "",
            "A split batch is invalid/incomplete if either summary or facts failed validation.",
            "",
            "| Model | Rep | Batch | Unified | Split total | Unified cost | Split total cost |",
            "|---|---:|---:|---|---|---:|---:|",
        ]
    )
    for (model, repetition, batch), group in groups.items():
        unified = group.get("unified")
        split_status = _split_outcome(group)
        unified_status = (
            "contract-valid" if unified and unified.get("status") == "ok" else "invalid/incomplete"
        )
        unified_cost = _role_cost(unified)
        split_cost = _split_cost(group)
        pair_cells = (
            model,
            repetition,
            batch,
            unified_status,
            split_status,
            unified_cost,
            split_cost,
        )
        lines.append("| " + " | ".join(_cell(value) for value in pair_cells) + " |")
    lines.extend(
        [
            "",
            "## Human review",
            "",
            "Summary quality: [owner review in `owner-notes.md`]",
            "Facts quality: [owner review in `owner-notes.md`]",
            "Global quality: [owner review in `owner-notes.md`]",
            "Paired quality: [owner review in `owner-notes.md`]",
            "",
            "This report is regenerated; the separate owner-notes file is never overwritten.",
            "",
        ]
    )
    _write_owner_notes(directory)
    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")


def _role_cost(row: dict[str, object] | None) -> str:
    if row is None:
        return "unknown"
    usage = row.get("usage", [])
    if not isinstance(usage, list) or not usage or not isinstance(usage[0], dict):
        return "unknown"
    cost = usage[0].get("cost")
    currency = usage[0].get("currency")
    return f"{cost} {currency}" if cost is not None and currency is not None else "unknown"


def _split_cost(group: dict[str, dict[str, object]]) -> str:
    summary = _cost_value(group.get("split-summary"))
    facts = _cost_value(group.get("split-facts"))
    if summary is None or facts is None or summary[1] != facts[1]:
        return "unknown"
    return f"{summary[0] + facts[0]} {summary[1]}"


def _cost_value(row: dict[str, object] | None) -> tuple[float, str] | None:
    if row is None:
        return None
    usage = row.get("usage", [])
    first = usage[0] if isinstance(usage, list) and usage else None
    if not isinstance(first, dict):
        return None
    value, currency = first.get("cost"), first.get("currency")
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isinstance(currency, str)
    ):
        return float(value), currency
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Render saved memory evaluation evidence offline")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = load_saved_plan(args.output)
    write_report(args.output, plan)


if __name__ == "__main__":
    main()
