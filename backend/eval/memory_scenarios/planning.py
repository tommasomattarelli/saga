from pydantic import JsonValue


def batch_plan(
    *,
    raw_turns: int,
    intermediate_limit: int,
    global_updates: int,
    batch_size: int,
    available_turns: int,
    resolution_turn: int,
) -> dict[str, JsonValue]:
    values = (
        raw_turns,
        intermediate_limit,
        global_updates,
        batch_size,
        available_turns,
        resolution_turn,
    )
    if any(type(value) is not int for value in values):
        raise ValueError("R, K, J, B, available turns, and resolution turn must be integers")
    if min(raw_turns, intermediate_limit, global_updates, available_turns) < 0:
        raise ValueError("R, K, J, and available turns must be nonnegative")
    if batch_size < 1 or resolution_turn < 1:
        raise ValueError("B and resolution turn must be positive")
    required = raw_turns + (intermediate_limit + global_updates) * batch_size
    completed_source_batches = max(available_turns - raw_turns, 0) // batch_size
    intermediate_turns = intermediate_limit * batch_size
    global_update_batches = min(
        global_updates, max(completed_source_batches - intermediate_limit, 0)
    )
    global_update_turns = global_update_batches * batch_size
    global_prefix = global_update_turns
    blockers: list[JsonValue] = []
    if available_turns < required:
        blockers.append("insufficient_source_length")
    if resolution_turn > global_prefix:
        blockers.append("resolution_after_eligible_global_prefix")
    return {
        "formula": "N = R + (K + J) * B",
        "R": raw_turns,
        "K": intermediate_limit,
        "J": global_updates,
        "B": batch_size,
        "required_turns": required,
        "available_turns": available_turns,
        "sufficient": available_turns >= required,
        "intermediate_turns": intermediate_turns,
        "global_update_turns": global_update_turns,
        "global_prefix_turns": global_prefix,
        "resolution_turn": resolution_turn,
        "resolution_in_global_prefix": resolution_turn <= global_prefix,
        "closure_eligible": not blockers,
        "closure_blockers": blockers,
        "incomplete_tail_turns": available_turns % batch_size,
    }
