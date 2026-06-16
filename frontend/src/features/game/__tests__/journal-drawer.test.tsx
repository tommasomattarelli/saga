import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import JournalDrawer from "../components/journal-drawer";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";
import type { Campaign } from "../../../shared/types";

const setup = (quests: unknown) => {
  useGameStore.setState({ campaign: { quests } as unknown as Campaign });
  useUIStore.setState({ sidePanel: "quests" });
};

describe("JournalDrawer", () => {
  it("shows the empty state when no active quests", () => {
    setup({ active: [], completed: [] });
    render(<JournalDrawer />);
    expect(screen.getByText("No oaths yet sworn.")).toBeInTheDocument();
    expect(screen.getByText("0 active · 0 completed")).toBeInTheDocument();
  });

  it("renders active quests and strips the [x] objective prefix", () => {
    setup({
      active: [
        {
          name: "Find the relic",
          description: "Seek it",
          status: "active",
          objectives: ["[x] Enter the cave", "Climb the peak"],
        },
      ],
      completed: [],
    });
    render(<JournalDrawer />);
    expect(screen.getByText("Find the relic")).toBeInTheDocument();
    expect(screen.getByText(/Enter the cave/)).toBeInTheDocument();
    expect(screen.getByText(/Climb the peak/)).toBeInTheDocument();
    expect(screen.getByText("1 active · 0 completed")).toBeInTheDocument();
  });

  it("renders the completed-deeds accordion with a count", () => {
    setup({
      active: [],
      completed: [{ name: "Slay the boar", description: "Done", status: "completed", objectives: [] }],
    });
    render(<JournalDrawer />);
    expect(screen.getByText("Completed Deeds")).toBeInTheDocument();
    expect(screen.getByText("(1)")).toBeInTheDocument();
  });
});
