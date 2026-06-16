import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import NPCBubble from "../components/npc-bubble";

describe("NPCBubble", () => {
  it("renders name and dialogue in quotes", () => {
    render(<NPCBubble npc_name="Gable" dialogue="Halt, traveler." />);
    expect(screen.getByText("Gable")).toBeInTheDocument();
    expect(screen.getByText(/Halt, traveler\./)).toBeInTheDocument();
  });

  it("renders the optional action only when provided", () => {
    const { rerender } = render(<NPCBubble npc_name="Gable" dialogue="Hi" />);
    expect(screen.queryByText(/draws a blade/)).not.toBeInTheDocument();
    rerender(<NPCBubble npc_name="Gable" dialogue="Hi" action="draws a blade" />);
    expect(screen.getByText(/draws a blade/)).toBeInTheDocument();
  });
});
