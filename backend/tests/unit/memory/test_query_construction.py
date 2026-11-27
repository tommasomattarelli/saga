from app.memory.context_snapshot import HistoryMessage
from app.memory.query_construction import build_gazetteer, build_scene_anchor


def _state() -> tuple[dict, dict]:
    baseline = {"nodes": {"thornhaven": {"name": "Thornhaven"}}}
    state = {
        "player_position": "thornhaven",
        "meta": {"current_location": "thornhaven"},
        "npcs": {
            "lyra": {"name": "Lyra", "slug": "lyra", "location": "thornhaven", "met_player": True},
            "aldric": {
                "name": "Aldric",
                "location": "thornhaven",
                "last_interactions": ["Aldric nodded."],
            },
            "morrowglass": {
                "name": "Morrowglass",
                "location": "thornhaven",
                "met_player": False,
            },
        },
    }
    return state, baseline


def test_anchor_uses_location_met_npcs_and_last_mentioned_name() -> None:
    state, baseline = _state()
    history: tuple[HistoryMessage, ...] = (
        HistoryMessage("assistant", "You enter the town."),
        HistoryMessage("user", "I ask Morrowglass about the key."),
    )

    anchor = build_scene_anchor(state, baseline, history)

    assert anchor.startswith("At Thornhaven, with ")
    assert "Aldric" in anchor and "Lyra" in anchor and "Morrowglass" in anchor


def test_anchor_can_be_disabled_and_capped() -> None:
    state, baseline = _state()
    assert build_scene_anchor(state, baseline, (), include_scene=False) == ""
    assert len(build_scene_anchor(state, baseline, (), max_chars=12)) == 12


def test_gazetteer_matches_baseline_and_fact_names() -> None:
    state, baseline = _state()
    names = build_gazetteer(state, baseline, ["Silver Key"])
    assert {"Thornhaven", "Lyra", "lyra", "Morrowglass", "Silver Key"} <= set(names)
