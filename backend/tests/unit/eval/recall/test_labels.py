import json

import pytest
from eval.recall.labels import RecallLabel, index_labels, load_labels


def _label(query: str, expected: tuple[str, ...]) -> RecallLabel:
    return RecallLabel(query=query, anchor="At Thornhaven, with Lyra.", expected=expected)


def test_load_labels_accepts_distinct_queries(tmp_path) -> None:
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps(
            [
                {
                    "query": "find the old map",
                    "anchor": "At Thornhaven, with Lyra.",
                    "expected": ["Lyra kept the old map."],
                },
                {
                    "query": "who guards the gate",
                    "anchor": "At the gate, with Aldric.",
                    "expected": ["Aldric guards the gate."],
                },
            ]
        )
    )
    assert load_labels(path) == (
        _label("find the old map", ("Lyra kept the old map.",)),
        RecallLabel(
            query="who guards the gate",
            anchor="At the gate, with Aldric.",
            expected=("Aldric guards the gate.",),
        ),
    )


def test_load_labels_rejects_duplicate_queries(tmp_path) -> None:
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps(
            [
                {"query": "same", "anchor": "", "expected": ["a"]},
                {"query": "same", "anchor": "", "expected": ["b"]},
            ]
        )
    )

    with pytest.raises(ValueError, match="unique"):
        load_labels(path)


def test_index_labels_maps_contents_to_zero_based_indices() -> None:
    labels = (
        _label("find the old map", ("Lyra kept the old map.", "Aldric saw it.")),
        _label("who guards the gate", ("Aldric guards the gate.",)),
    )
    facts = ("Aldric saw it.", "Lyra kept the old map.", "Aldric guards the gate.")

    assert index_labels(labels, facts) == ((1, 0), (2,))


def test_index_labels_rejects_unknown_or_ambiguous_facts() -> None:
    facts = ("Lyra kept the old map.", "Lyra kept the old map.")

    with pytest.raises(ValueError, match="not unique"):
        index_labels((_label("find the old map", ("Lyra kept the old map.",)),), facts)

    with pytest.raises(ValueError, match="unknown"):
        index_labels((_label("find the old map", ("missing fact",)),), facts)
