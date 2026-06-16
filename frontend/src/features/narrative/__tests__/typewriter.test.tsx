import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("../hooks/use-typewriter", () => ({ useTypewriter: vi.fn() }));
import Typewriter from "../components/typewriter";
import { useTypewriter } from "../hooks/use-typewriter";

describe("Typewriter", () => {
  it("renders the typed text across paragraphs", () => {
    vi.mocked(useTypewriter).mockReturnValue({ displayed: "First line\nSecond line", isTyping: false, skip: () => {} });
    render(<Typewriter text="ignored" />);
    expect(screen.getByText("First line")).toBeInTheDocument();
    expect(screen.getByText("Second line")).toBeInTheDocument();
  });

  it("renders a drop-cap for the first character when dropCap is set", () => {
    vi.mocked(useTypewriter).mockReturnValue({ displayed: "Alpha", isTyping: false, skip: () => {} });
    render(<Typewriter text="ignored" dropCap />);
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText(/lpha/)).toBeInTheDocument();
  });
});
