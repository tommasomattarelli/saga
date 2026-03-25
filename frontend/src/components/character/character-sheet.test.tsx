import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CharacterSheet from "./character-sheet";
import { useGameStore } from "../../stores/game-store";
import "@testing-library/jest-dom";
import type { Campaign, CharacterData } from "../../types";

describe("CharacterSheet Component", () => {
  const mockChar: CharacterData = {
    name: "Grog",
    level: 5,
    xp: 2500,
    hp: 45,
    max_hp: 50,
    ac: 16,
    abilities: { strength: 18, dexterity: 12 },
    skills: { athletics: { level: 2, uses: 0, progress: 0 } },
    inventory: [{ name: "Axe", quantity: 1, type: "weapon" }],
    equipped: {},
    gold: 100,
    background: "Noble",
    notes: "Tough guy",
    reputation: {},
    active_quests: [],
  };

  const createMockCampaign = (charData: CharacterData | null): Campaign => ({
    id: "c1",
    name: "Test",
    template_id: "t1",
    status: "active",
    death_mode: "destino",
    turn_number: 1,
    character_data: charData as CharacterData, // if null, we test fallback and it's fine for mock
    world_state: {},
    quests: {},
    created_at: "now",
    updated_at: "now",
  });

  it("should render character basic info", () => {
    useGameStore.setState({
      campaign: createMockCampaign(mockChar),
    });

    render(<CharacterSheet />);

    expect(screen.getByText(/Grog/i)).toBeInTheDocument();
    expect(screen.getByText(/Level 5/i)).toBeInTheDocument();
    expect(screen.getByText("45/50")).toBeInTheDocument();
    expect(screen.getByText(/STR/i)).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("+4")).toBeInTheDocument(); // 18 -> +4
    expect(screen.getByText(/Athletics/i)).toBeInTheDocument();
    expect(screen.getByText(/Axe/i)).toBeInTheDocument();
  });

  it("should render empty inventory correctly", () => {
    const emptyChar = { ...mockChar, inventory: [], gold: 0 };
    useGameStore.setState({ campaign: createMockCampaign(emptyChar) });
    render(<CharacterSheet />);
    expect(screen.getByText("Empty")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("should correctly handle negative ability modifiers", () => {
    useGameStore.setState({
      campaign: createMockCampaign({ ...mockChar, abilities: { dexterity: 8 } }),
    });
    render(<CharacterSheet />);
    expect(screen.getByText(/DEX/i)).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("-1")).toBeInTheDocument();
  });

  it("should show empty state if no character data", () => {
    // We cast to any for a negative test of null data
    useGameStore.setState({ campaign: createMockCampaign(null as unknown as CharacterData) });
    render(<CharacterSheet />);
    expect(screen.getByText("No character data")).toBeInTheDocument();
  });

  it("should show empty state if no campaign", () => {
    useGameStore.setState({ campaign: null });
    const { container } = render(<CharacterSheet />);
    expect(container.firstChild).toBeNull();
  });
});
