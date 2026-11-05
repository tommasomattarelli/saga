import json
from pathlib import Path

from ledger import RequestLedger

from cache.plan import Plan


def write_report(directory: Path, plan: Plan) -> None:
    ledger = RequestLedger(directory / "requests.jsonl")
    metadata_path = directory / "metadata.jsonl"
    metadata = {
        row["id"]: row
        for line in (metadata_path.read_text().splitlines() if metadata_path.exists() else [])
        if line.strip()
        for row in [json.loads(line)]
    }
    lines = [
        f"# Cache probe — {plan.model} / {plan.phase}",
        f"\nRun: `{plan.run_id}`. Attempts: {ledger.spent}/8. "
        f"Interrupted: {len(ledger.interrupted())}. Output cap: {plan.max_tokens}.",
        "\nA completed/truncated response is transport evidence, not narrative acceptance.",
        "Missing fields are unknown. Cost is provider-reported; currency is not inferred.",
        "\n| # | Regime | Trial/step | Payload | Status/finish | Input | Cached | Write | Output | Reasoning | Cost | Currency | Provider | Endpoint attempts | Seconds | Gap s | Generation |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for request, attempt in zip(plan.requests, ledger.results(), strict=False):
        usage = attempt.usage[0] if attempt.usage else {}
        response = attempt.response
        generation_id = response.get("id")
        meta = metadata.get(generation_id, {}).get("data", {})
        endpoints = meta.get("provider_responses")
        endpoint_text = (
            ", ".join(
                f"{item.get('endpoint_id', '?')}:{item.get('status', '?')}" for item in endpoints
            )
            if isinstance(endpoints, list)
            else None
        )
        cells = [
            request.index + 1,
            request.regime,
            f"{request.trial + 1}/{request.step + 1}",
            request.payload,
            f"{attempt.status}/{response.get('finish_reason', '?')}",
            usage.get("input_tokens"),
            usage.get("cached_input_tokens"),
            response.get("cache_write_tokens"),
            usage.get("output_tokens"),
            usage.get("reasoning_output_tokens"),
            usage.get("cost"),
            usage.get("currency"),
            meta.get("provider_name", response.get("provider")),
            endpoint_text,
            round(attempt.seconds, 3),
            attempt.correlation.get("gap_seconds"),
            generation_id,
        ]
        lines.append(
            "| "
            + " | ".join(
                "unknown" if value is None else str(value).replace("|", "\\|").replace("\n", " ")
                for value in cells
            )
            + " |"
        )
    for regime in ("per-trial", "shared"):
        attempts = [a for a in ledger.results() if a.correlation.get("regime") == regime]
        usages = [a.usage[0] for a in attempts if a.usage]
        paired = [
            u
            for u in usages
            if u.get("input_tokens") is not None and u.get("cached_input_tokens") is not None
        ]
        inputs = sum(u["input_tokens"] for u in paired)
        cached = sum(u["cached_input_tokens"] for u in paired)
        hits = sum(u["cached_input_tokens"] > 0 for u in paired)
        fraction = f"{cached / inputs:.2%}" if inputs else "unknown"
        lines.append(
            f"\n- {regime}: {hits}/{len(paired)} reported hits; {fraction} cached input "
            f"on paired usage; {len(attempts) - len(paired)} missing pairs."
        )
    lines.extend(
        [
            "\n## Interpretation",
            *[f"- {note}" for note in plan.limitations],
            "\n## Owner dashboard review",
            "\nRecord observations and the actual pause in a separate owner-notes.md; this report is regenerated.",
        ]
    )
    (directory / "report.md").write_text("\n".join(lines) + "\n")
