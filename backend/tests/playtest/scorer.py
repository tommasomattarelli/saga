"""Narrative quality scorer for playtests."""


def score_narration(narration: str) -> dict:
    """Score the quality of a DM narration.

    Returns quality metrics (heuristic, will be enhanced with AI scoring).
    """
    scores = {
        "length_ok": 50 <= len(narration) <= 3000,
        "has_dialogue": '"' in narration or "\u2018" in narration,
        "has_sensory_detail": any(
            word in narration.lower()
            for word in [
                "smell",
                "sound",
                "feel",
                "see",
                "hear",
                "taste",
                "cold",
                "warm",
                "dark",
                "light",
            ]
        ),
        "second_person": narration.lower().startswith("you") or " you " in narration.lower(),
        "not_repetitive": len(set(narration.split())) / max(len(narration.split()), 1) > 0.4,
    }
    scores["total"] = sum(scores.values()) / len(scores)
    return scores
