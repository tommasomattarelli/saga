from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class RecallLabel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    query: str = Field(min_length=1)
    anchor: str = ""
    expected: tuple[str, ...] = Field(min_length=1)


def load_labels(path: Path) -> tuple[RecallLabel, ...]:
    labels = tuple(
        RecallLabel.model_validate_json(json.dumps(item))
        for item in json.loads(path.read_text(encoding="utf-8"))
    )
    if not labels:
        raise ValueError("Recall labels must not be empty.")
    queries = [label.query for label in labels]
    if len(set(queries)) != len(queries):
        raise ValueError("Recall labels must have unique queries.")
    return labels


def index_labels(
    labels: Sequence[RecallLabel], facts: Sequence[str]
) -> tuple[tuple[int, ...], ...]:
    positions: dict[str, list[int]] = {}
    for index, content in enumerate(facts):
        positions.setdefault(content, []).append(index)
    indexed: list[tuple[int, ...]] = []
    for label in labels:
        expected: list[int] = []
        for content in label.expected:
            matches = positions.get(content, ())
            if len(matches) > 1:
                raise ValueError(f"Expected fact is not unique: {content}")
            if not matches:
                raise ValueError(f"Expected fact is unknown: {content}")
            expected.append(matches[0])
        indexed.append(tuple(expected))
    return tuple(indexed)
