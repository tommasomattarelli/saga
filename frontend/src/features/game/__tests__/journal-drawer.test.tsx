import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import JournalDrawer from "../components/journal-drawer";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";
import type { Campaign, QuestRegistry } from "../../../shared/types";

const setup = (quests: QuestRegistry) => {
  useGameStore.setState({ campaign: { quests } as unknown as Campaign });
  useUIStore.setState({ sidePanel: "quests" });
};

const empty: QuestRegistry = { active: [], completed: [], failed: [], abandoned: [] };

describe("JournalDrawer", () => {
  it("shows the empty state when no active quests", () => {
    setup(empty);
    render(<JournalDrawer />);
    expect(screen.getByText("No quests yet.")).toBeInTheDocument();
    expect(screen.getByText("0 active · 0 concluded")).toBeInTheDocument();
  });

  it("renders active quests and strips the [x] objective prefix", () => {
    setup({
      ...empty,
      active: [
        {
          id: "find_relic",
          name: "Find the relic",
          description: "Seek it",
          objectives: ["[x] Enter the cave", "Climb the peak"],
        },
      ],
    });
    render(<JournalDrawer />);
    expect(screen.getByText("Find the relic")).toBeInTheDocument();
    expect(screen.getByText(/Enter the cave/)).toBeInTheDocument();
    expect(screen.getByText(/Climb the peak/)).toBeInTheDocument();
    expect(screen.getByText("1 active · 0 concluded")).toBeInTheDocument();
  });

  it("derives one record's status from its containing list", () => {
    setup({
      ...empty,
      active: [{ id: "boar", name: "Slay the boar", description: "Hunt it", objectives: [] }],
      completed: [
        {
          id: "guide",
          name: "Find the guide",
          description: "Done",
          objectives: [],
        },
      ],
    });
    render(<JournalDrawer />);
    fireEvent.click(screen.getByText("Concluded (1)"));
    expect(screen.getByText("Find the guide").closest("h4")?.style.textDecoration).toBe(
      "line-through",
    );
    expect(screen.getByText("Slay the boar").closest("h4")?.style.textDecoration).toBe("none");
  });

  it("renders completed, failed and abandoned quests in the concluded accordion", () => {
    setup({
      ...empty,
      completed: [{ id: "done", name: "Done Quest", description: "", objectives: [] }],
      failed: [{ id: "lost", name: "Lost Quest", description: "", objectives: [] }],
      abandoned: [{ id: "left", name: "Left Quest", description: "", objectives: [] }],
    });
    render(<JournalDrawer />);
    expect(screen.getByText("Concluded (3)")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Concluded (3)"));
    expect(screen.getByText("Done Quest")).toBeInTheDocument();
    expect(screen.getByText("Lost Quest")).toBeInTheDocument();
    expect(screen.getByText("Left Quest")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Abandoned")).toBeInTheDocument();
  });
});
