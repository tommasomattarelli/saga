import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Drawer } from "../drawer";

describe("Drawer", () => {
  it("renders title and children when open", () => {
    render(
      <Drawer open={true} onClose={() => {}} title="The Ledger">
        <p>Drawer content</p>
      </Drawer>
    );
    expect(screen.getByText("The Ledger")).toBeInTheDocument();
    expect(screen.getByText("Drawer content")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(
      <Drawer open={false} onClose={() => {}} title="Hidden">
        <p>Hidden content</p>
      </Drawer>
    );
    expect(screen.queryByText("Hidden")).not.toBeInTheDocument();
  });

  it("calls onClose when close button is clicked", () => {
    const onClose = vi.fn();
    render(
      <Drawer open={true} onClose={onClose} title="Closeable">
        content
      </Drawer>
    );
    fireEvent.click(screen.getByRole("button", { name: /close drawer/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
