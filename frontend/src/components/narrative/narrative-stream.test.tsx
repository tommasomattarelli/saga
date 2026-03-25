import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import NarrativeStream from "./narrative-stream";
import { useGameStore } from "../../stores/game-store";
import type { GameWebSocket } from "../../services/websocket";
import "@testing-library/jest-dom";

describe("NarrativeStream Component", () => {
  const wsRef = React.createRef<GameWebSocket | null>();

  beforeEach(() => {
    useGameStore.setState({
      turnHistory: [],
      isProcessing: false,
    });
  });

  it("should show empty state message when no turns", () => {
    render(<NarrativeStream wsRef={wsRef} />);
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
          model_used: "model-x",
          invoke_npcs: [],
          time_passed_minutes: 5,
          ambient_detail: null,
          requires_player_action: true,
        },
      ],
    });

    render(<NarrativeStream wsRef={wsRef} />);
    expect(screen.getByText("A dark forest surrounds you.")).toBeInTheDocument();
    expect(screen.getByText("Look around")).toBeInTheDocument();
  });

  it("should show processing state", () => {
    useGameStore.setState({ isProcessing: true });
    render(<NarrativeStream wsRef={wsRef} />);
    expect(screen.getByText("The DM considers your action")).toBeInTheDocument();
  });
});
