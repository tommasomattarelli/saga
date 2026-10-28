import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import NPCBubble from "../components/npc-bubble";

describe("NPCBubble", () => {
  it("renders name and dialogue in quotes", () => {
    render(<NPCBubble npc_name="Gable" dialogue="Halt, traveler." />);
    expect(screen.getByText("Gable")).toBeInTheDocument();
    expect(screen.getByText(/Halt, traveler\./)).toBeInTheDocument();
  });

  it("renders speech without adding an action", () => {
    render(<NPCBubble npc_name="Gable" dialogue="Hi" />);
    expect(screen.getByText(/Hi/)).toBeInTheDocument();
    expect(screen.queryByText(/draws a blade/)).not.toBeInTheDocument();
  });
});
