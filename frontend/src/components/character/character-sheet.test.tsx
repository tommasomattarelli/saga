import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CharacterSheet from "./character-sheet";
import { useGameStore } from "../../stores/game-store";
import "@testing-library/jest-dom";

describe("CharacterSheet Component", () => {
  const mockChar = {
    name: "Grog",
    level: 5,
    xp: 2500,
    hp: 45,
    max_hp: 50,
    ac: 16,
    abilities: { strength: 18, dexterity: 12 },
    skills: { athletics: { level: 2, uses: 0, progress: 0 } },
    inventory: [{ name: "Axe", quantity: 1, type: "weapon" }],
    gold: 100,
  };

  it("should render character basic info", () => {
    useGameStore.setState({
      campaign: {
        character_data: mockChar,
      } as any,
    });

    render(<CharacterSheet />);
    
    expect(screen.getByText("Grog")).toBeInTheDocument();
    expect(screen.getByText("Level 5")).toBeInTheDocument();
    expect(screen.getByText("45/50")).toBeInTheDocument();
    expect(screen.getByText("AC:")).toBeInTheDocument();
    expect(screen.getByText("16")).toBeInTheDocument();
  });

  it("should show empty state if no campaign", () => {
    useGameStore.setState({ campaign: null });
    const { container } = render(<CharacterSheet />);
    expect(container.firstChild).toBeNull();
  });
});
