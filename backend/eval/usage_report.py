"""Offline CSV and Markdown summaries for persisted per-request usage."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict

from app.ai.providers.usage import UsageMetadata


def _items(row: dict) -> list[dict]:
    usages = row.get("usage") or [None]
    correlation = row.get("correlation") or {}
    return [
        {**correlation, **(asdict(item) if isinstance(item, UsageMetadata) else item or {})}
        for item in usages
    ]


def usage_csv(rows: Iterable[dict]) -> str:
    output = io.StringIO()
    columns = (
        "key",
        "ledger",
        "model",
        "scenario",
        "probe",
        "role",
        "step",
        "beat",
        "npc_id",
        "npc_name",
        "response_id",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_input_tokens",
        "reasoning_output_tokens",
        "cost",
        "currency",
        "seconds",
    )
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        for item in _items(row):
            writer.writerow({**row, **item})
    return output.getvalue()


def _label(value: object | None) -> str:
    return "" if value is None else str(value)


def _sum(items: list[dict], field: str) -> str:
    values = [item.get(field) for item in items]
    present = [
        value
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return str(sum(present)) if present else "—"


def usage_markdown(rows: Iterable[dict]) -> str:
    groups: dict[tuple[str, str, str, str, str], list[tuple[dict, dict]]] = defaultdict(list)
    for row in rows:
        for item in _items(row):
            key = (
                _label(row.get("model")),
                _label(row.get("scenario")),
                _label(item.get("step")),
                _label(item.get("role")),
                _label(item.get("npc_id")),
            )
            groups[key].append((row, item))
    columns = (
        "Model",
        "Case",
        "Step",
        "Role",
        "Actor",
        "Requests",
        "Input",
        "Output",
        "Total",
        "Missing input",
        "Missing output",
        "Missing total",
        "Cached",
        "Reasoning",
        "Latency s",
        "Cost",
    )
    output = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for key in sorted(groups):
        entries = groups[key]
        items = [item for _, item in entries]
        missing = [
            sum(item.get(field) is None for item in items)
            for field in ("input_tokens", "output_tokens", "total_tokens")
        ]
        costs: dict[str | None, list[dict]] = defaultdict(list)
        for item in items:
            if isinstance(item.get("cost"), (int, float)) and not isinstance(
                item.get("cost"), bool
            ):
                costs[item.get("currency")].append(item)
        cost_text = (
            ", ".join(
                f"{currency or 'unspecified'} {_sum(cost_rows, 'cost')}"
                for currency, cost_rows in sorted(costs.items(), key=lambda pair: pair[0] or "")
            )
            or "—"
        )
        values = [
            *key,
            str(len(entries)),
            _sum(items, "input_tokens"),
            _sum(items, "output_tokens"),
            _sum(items, "total_tokens"),
            *(str(value) for value in missing),
            _sum(items, "cached_input_tokens"),
            _sum(items, "reasoning_output_tokens"),
            _sum([row for row, _ in entries], "seconds"),
            cost_text,
        ]
        output.append("| " + " | ".join(values) + " |")
    return "\n".join(output) + "\n"
