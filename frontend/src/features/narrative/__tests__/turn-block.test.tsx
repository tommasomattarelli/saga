import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TurnBlock from "../components/turn-block";
import { useUIStore } from "../../../shared/stores/ui-store";
import type { DiceRollResult, TurnResponse } from "../../../shared/types";

const roll: DiceRollResult = {
  expression: "1d20+2",
  rolls: [15],
  modifier: 2,
  total: 17,
  difficulty: "normal",
  difficulty_draw: 0,
  success: true,
  outcome: "full_success",
  is_critical: false,
};

function turn(overrides: Partial<TurnResponse> = {}): TurnResponse {
  return {
    turn_number: 2,
    player_action: "Look around",
    narration: "A quiet evening.\nA cold wind.",
    scene_mood: "quiet",
    ...overrides,
  };
}

function segmentedTurn(): TurnResponse {
  return turn({
    narration_segments: [
      {
        step: 1,
        text: "You reach the gate.\nA guard waits.",
        dice: { inline: { ...roll, rolls: [3], total: 5 } },
        npc_dialogues: [{ npc_name: "Guide", dialogue: "Careful", action: "whispers" }],
      },
      { step: 2, text: "The gate opens.", dice: { Lock: roll }, npc_dialogues: [] },
      { step: 3, text: "A courtyard lies beyond.", dice: null, npc_dialogues: [] },
    ],
    dice_results: [{ step: 1, rolls: { Gate: roll } }],
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(Math, "random").mockReturnValue(0.5);
  useUIStore.setState({ soundEnabled: false });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("Turn presentation and dice gating", () => {
  it("renders historical segments and NPC dialogue using authoritative dice results", () => {
    render(
      <TurnBlock turn={segmentedTurn()} isLatest={false} isFresh={false} isFirst showDivider />,
    );
    expect(screen.getByText("Look around")).toBeInTheDocument();
    expect(screen.getByText("A guard waits.")).toBeInTheDocument();
    expect(screen.getByText(/Careful/)).toBeInTheDocument();
    expect(screen.getByText("The gate opens.")).toBeInTheDocument();
    expect(screen.getByText("A courtyard lies beyond.")).toBeInTheDocument();
    expect(screen.getAllByText("17")).toHaveLength(2);
    expect(screen.queryByText("inline")).not.toBeInTheDocument();
    expect(screen.getByRole("separator", { hidden: true })).toBeInTheDocument();
  });

  it("reveals each live segment only after its dice and notifies after the final roll", async () => {
    const onAllDiceRevealed = vi.fn();
    render(
      <TurnBlock
        turn={segmentedTurn()}
        isLatest
        isFresh={false}
        isFirst={false}
        showDivider={false}
        onAllDiceRevealed={onAllDiceRevealed}
      />,
    );
    expect(screen.queryByText("The gate opens.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Roll"));
    await act(async () => vi.runAllTimersAsync());
    expect(screen.getByText("The gate opens.")).toBeInTheDocument();
    expect(screen.queryByText("A courtyard lies beyond.")).not.toBeInTheDocument();
    expect(onAllDiceRevealed).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Roll"));
    await act(async () => vi.runAllTimersAsync());
    expect(screen.getByText("A courtyard lies beyond.")).toBeInTheDocument();
    expect(onAllDiceRevealed).toHaveBeenCalledOnce();
  });

  it("supports legacy journal turns and their dice callback", async () => {
    const onAllDiceRevealed = vi.fn();
    render(
      <TurnBlock
        turn={turn({ dice_rolls: { Save: roll }, narration_segments: [] })}
        isLatest
        isFresh={false}
        isFirst={false}
        showDivider={false}
        onAllDiceRevealed={onAllDiceRevealed}
      />,
    );
    expect(screen.getByText("A quiet evening.")).toBeInTheDocument();
    expect(screen.getByText("A cold wind.")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Roll"));
    await act(async () => vi.runAllTimersAsync());
    expect(onAllDiceRevealed).toHaveBeenCalledOnce();
  });

  it("animates fresh narration without requiring a player action or completion callback", async () => {
    const narration = "A new beginning.";
    render(
      <TurnBlock
        turn={turn({ player_action: undefined, narration })}
        isLatest
        isFresh
        isFirst={false}
        showDivider={false}
      />,
    );
    for (let step = 0; step < narration.length; step++) {
      await act(async () => vi.advanceTimersByTimeAsync(500));
    }
    expect(screen.getByText(narration)).toBeInTheDocument();
    expect(screen.queryByText("Look around")).not.toBeInTheDocument();
  });
});
