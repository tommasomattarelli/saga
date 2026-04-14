import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import NarrativeStream from "./narrative-stream";
import { useGameStore } from "../../stores/game-store";
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
    expect(screen.getByText("Your adventure awaits…")).toBeInTheDocument();
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
    // Latest turn uses typewriter — wait for full text to render
    await waitFor(
      () => expect(screen.getByText("A dark forest surrounds you.")).toBeInTheDocument(),
      { timeout: 5000 },
    );
  });

  it("should show loading state", () => {
    useGameStore.setState({ isLoading: true, pendingAction: "Walk forward" });
    render(<NarrativeStream />);
    expect(screen.getByText("The DM considers your action…")).toBeInTheDocument();
  });

  it("should show pending action bubble while loading", () => {
    useGameStore.setState({ isLoading: true, pendingAction: "Walk forward" });
    render(<NarrativeStream />);
    expect(screen.getByText("Walk forward")).toBeInTheDocument();
  });

  it("should use scrollRef when provided", () => {
    const scrollRef = React.createRef<HTMLDivElement | null>();
    render(<NarrativeStream scrollRef={scrollRef} />);
    expect(screen.getByText("Your adventure awaits…")).toBeInTheDocument();
  });
});
