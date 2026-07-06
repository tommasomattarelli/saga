import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CompanionBar from "../components/companion-bar";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";
import "@testing-library/jest-dom";
import type { Campaign, CharacterData, WorldState } from "../../../shared/types";

describe("CompanionBar Component", () => {
  const createMockCampaign = (worldState: WorldState): Campaign => ({
    id: "c1",
    name: "Test",
    world_slug: "w1",
    status: "active",
    death_mode: "destino",
    turn_number: 1,
    character_data: {} as CharacterData,
    world_state: worldState,
    quests: {},
    created_at: "now",
    updated_at: "now",
  });

  it("should render companions when visible and data exists", () => {
    useUIStore.setState({ showCompanionBar: true });
    useGameStore.setState({
      campaign: createMockCampaign({
        companions: {
          c1: {
            name: "Bob",
            hp: 10,
            max_hp: 20,
            mood: "Happy",
            loyalty: 5,
            trust: 10,
            personality: "Kind",
          },
        },
      }),
    });

    render(<CompanionBar />);

    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getByText("Happy")).toBeInTheDocument();
  });

  it("should return null if showCompanionBar is false", () => {
    useUIStore.setState({ showCompanionBar: false });
    const { container } = render(<CompanionBar />);
    expect(container.firstChild).toBeNull();
  });

  it("should return null if no companions in world_state", () => {
    useUIStore.setState({ showCompanionBar: true });
    useGameStore.setState({
      campaign: createMockCampaign({ companions: undefined }),
    });
    const { container } = render(<CompanionBar />);
    expect(container.firstChild).toBeNull();
  });
});
