"""The derive pass has to reproduce what production would have stored, not a
richer version of it — a fixture that is easier than reality measures nothing."""

import pytest
from derive import call_budget, resolve_recall, summary_context

_CORPUS = [
    {"turn": 3, "entity_name": "Lyra", "content": "Lyra held back at the bend."},
    {"turn": 9, "entity_name": "lyra", "content": "Lyra named the mine boards."},
    {"turn": 11, "entity_name": "Aldric", "content": "Aldric would not look up."},
    {"turn": 14, "entity_name": "Lyra", "content": "Lyra refused to go further."},
    {"turn": 0, "canary": "marta_coin", "content": "Marta refused to name the smith."},
]

# Four batch summaries over turns 1-17, as ensure_compression would write them:
# one summary per batch, copied onto every turn the batch covers.
_BATCHES = {"1-5": "alpha", "6-10": "beta", "11-15": "gamma", "16-17": "delta"}


def _per_turn() -> dict[int, str]:
    spread = {}
    for key, summary in _BATCHES.items():
        low, high = (int(n) for n in key.split("-"))
        for turn in range(low, high + 1):
            spread[turn] = f"[Turns {key}] {summary}"
    return spread


def test_only_the_batches_the_reader_would_reach_are_kept():
    """context._load_batch_summaries takes the last five turn *rows* below the
    window, so turns 13-17 resolve to two distinct summaries — not all four."""
    assert summary_context(_per_turn(), oldest_in_window=18) == (
        "[Turns 11-15] gamma\n[Turns 16-17] delta"
    )


def test_five_rows_inside_one_batch_yield_a_single_summary():
    """Turns 6-10 fill the five-row budget by themselves, so the batch before them
    never reaches the prompt however much history exists behind it."""
    assert summary_context(_per_turn(), oldest_in_window=11) == "[Turns 6-10] beta"


def test_no_summaries_below_the_window_yields_nothing():
    assert summary_context(_per_turn(), oldest_in_window=1) == ""


@pytest.mark.parametrize(
    ("turns", "window", "expected"),
    [
        (25, 8, {"compression": 4, "global_summary": 5, "facts": 25}),
        (8, 8, {"compression": 0, "global_summary": 1, "facts": 8}),
        (26, 8, {"compression": 4, "global_summary": 5, "facts": 26}),
    ],
)
def test_call_budget(turns, window, expected):
    assert call_budget(turns, window) == expected


def test_recall_resolves_canaries_and_entities():
    recall = resolve_recall({"p": {"recall": ["marta_coin", "Aldric"]}}, _CORPUS)
    assert recall["p"] == ["Marta refused to name the smith.", "Aldric would not look up."]


def test_recall_matches_entity_names_case_insensitively():
    recall = resolve_recall({"p": {"recall": ["LYRA"]}}, _CORPUS)
    assert len(recall["p"]) == 3


def test_recall_is_capped_at_the_production_limit():
    """context._recall_memories asks pgvector for three; handing the DM more would
    inflate the fixture past anything the engine builds."""
    recall = resolve_recall({"p": {"recall": ["Lyra", "Aldric", "marta_coin"]}}, _CORPUS)
    assert len(recall["p"]) == 3


def test_probe_without_recall_gets_nothing():
    assert resolve_recall({"p": {"player": "I wait."}}, _CORPUS) == {"p": []}


def test_unresolvable_token_is_fatal():
    with pytest.raises(SystemExit, match="ghost"):
        resolve_recall({"p": {"recall": ["ghost"]}}, _CORPUS)
