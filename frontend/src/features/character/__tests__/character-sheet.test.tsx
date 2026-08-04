import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CharacterSheet from "../components/character-sheet";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";
import "@testing-library/jest-dom";
import type { Campaign, CharacterData } from "../../../shared/types";

describe("CharacterSheet Component", () => {
  const mockChar: CharacterData = {
    name: "Grog",
    level: 5,
    xp: 2500,
    hp: { current: 45, max: 50 },
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
    world_slug: "w1",
    status: "active",
    difficulty: "medium",
    turn_number: 1,
    character_data: charData as CharacterData,
    world_state: {},
    quests: {},
    created_at: "now",
    updated_at: "now",
  });

  it("should render character basic info", () => {
    useGameStore.setState({
      campaign: createMockCampaign(mockChar),
    });
    useUIStore.setState({ sidePanel: "character" });

    render(<CharacterSheet />);

    expect(screen.getByText(/Grog/i)).toBeInTheDocument();
    expect(screen.getByText(/Lv 5/i)).toBeInTheDocument();
    expect(screen.getByText(/HP 45\/50/)).toBeInTheDocument();
    // Stats tab is the default
    expect(screen.getByText(/strength/i)).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("+4")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Skills"));
    expect(screen.getByText(/athletics/i)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Inventory"));
    expect(screen.getByText(/Axe/i)).toBeInTheDocument();
  });

  it("should render empty inventory correctly", () => {
    const emptyChar = { ...mockChar, inventory: [], gold: 0 };
    useGameStore.setState({ campaign: createMockCampaign(emptyChar) });
    useUIStore.setState({ sidePanel: "character" });
    render(<CharacterSheet />);
    fireEvent.click(screen.getByText("Inventory"));
    expect(screen.getByText("Nothing carried yet.")).toBeInTheDocument();
  });

  it("should correctly handle negative ability modifiers", () => {
    useGameStore.setState({
      campaign: createMockCampaign({ ...mockChar, abilities: { dexterity: 8 } }),
    });
    useUIStore.setState({ sidePanel: "character" });
    render(<CharacterSheet />);
    expect(screen.getByText(/dexterity/i)).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("-1")).toBeInTheDocument();
  });

  it("should show empty state if no character data", () => {
    useGameStore.setState({ campaign: createMockCampaign(null as unknown as CharacterData) });
    useUIStore.setState({ sidePanel: "character" });
    render(<CharacterSheet />);
    expect(screen.getByText("No character data.")).toBeInTheDocument();
  });

  it("should show empty state if no campaign", () => {
    useGameStore.setState({ campaign: null });
    const { container } = render(<CharacterSheet />);
    expect(container.firstChild).toBeNull();
  });
});
