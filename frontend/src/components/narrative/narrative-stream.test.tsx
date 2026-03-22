import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import NarrativeStream from "./narrative-stream";
import { useGameStore } from "../../stores/game-store";
import "@testing-library/jest-dom";

describe("NarrativeStream Component", () => {
  beforeEach(() => {
    useGameStore.setState({
      turnHistory: [],
      isProcessing: false,
    });
  });

  it("should show empty state message when no turns", () => {
    render(<NarrativeStream />);
    expect(screen.getByText("Your adventure awaits...")).toBeInTheDocument();
  });

  it("should render turn history properly", () => {
    useGameStore.setState({
      turnHistory: [
        {
          turn_number: 1,
          narration: "A dark forest surrounds you.",
          dice_rolls: null,
          companion_actions: null,
          world_updates: null,
          scene_mood: "dark",
          suggested_actions: ["Look around"],
          model_used: "model-x"
        }
      ],
    });

    render(<NarrativeStream />);
    expect(screen.getByText("A dark forest surrounds you.")).toBeInTheDocument();
    expect(screen.getByText("Look around")).toBeInTheDocument();
  });

  it("should show processing state", () => {
    useGameStore.setState({ isProcessing: true });
    render(<NarrativeStream />);
    expect(screen.getByText("The DM considers your action")).toBeInTheDocument();
  });
});
