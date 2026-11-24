def integrated_source(turn_count: int = 52) -> dict[str, object]:
    return {
        "turns": [
            {
                "reference": f"t{index}",
                "turn_id": f"00000000-0000-0000-0000-{index:012d}",
                "player_action": "Act",
                "narration": "Result",
                "operations": None,
            }
            for index in range(1, turn_count + 1)
        ]
    }
