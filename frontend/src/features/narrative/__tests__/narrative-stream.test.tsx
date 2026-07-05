import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import NarrativeStream from "../components/narrative-stream";
import { useGameStore } from "../../../shared/stores/game-store";
import "@testing-library/jest-dom";

describe("NarrativeStream Component", () => {
  beforeEach(() => {
    useGameStore.setState({
      turnHistory: [],
      isLoading: false,
      pendingAction: null,
    });
  });

  it("should show empty state message when no turns", () => {
    render(<NarrativeStream />);
    expect(screen.getByText("The story hasn't started yet")).toBeInTheDocument();
  });

  it("should render turn history properly", async () => {
    useGameStore.setState({
      turnHistory: [
        {
          turn_number: 1,
          narration: "A dark forest surrounds you.",
          dice_rolls: null,
          scene_mood: "dark",
          model_used: "model-x",
          requires_player_action: true,
        },
      ],
    });

    render(<NarrativeStream />);
    // Drop-cap splits the first letter into its own span, so match the remainder.
    expect(screen.getByText(/dark forest surrounds you/)).toBeInTheDocument();
  });

  it("should show loading state", () => {
    useGameStore.setState({ isLoading: true, pendingAction: "Walk forward" });
    render(<NarrativeStream />);
    expect(screen.getByTestId("dm-loading")).toBeInTheDocument();
  });

  it("should show pending action bubble while loading", () => {
    useGameStore.setState({ isLoading: true, pendingAction: "Walk forward" });
    render(<NarrativeStream />);
    expect(screen.getByText("Walk forward")).toBeInTheDocument();
  });

  it("should use scrollRef when provided", () => {
    const scrollRef = React.createRef<HTMLDivElement | null>();
    render(<NarrativeStream scrollRef={scrollRef} />);
    expect(screen.getByText("The story hasn't started yet")).toBeInTheDocument();
  });
});
