import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ConfirmModal } from "../modal";

const base = {
  onClose: vi.fn(),
  onConfirm: vi.fn(),
  title: "Delete?",
  description: "This is permanent.",
};

describe("ConfirmModal", () => {
  it("renders title and description when open", () => {
    render(<ConfirmModal open {...base} />);
    expect(screen.getByText("Delete?")).toBeInTheDocument();
    expect(screen.getByText("This is permanent.")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(<ConfirmModal open={false} {...base} />);
    expect(screen.queryByText("Delete?")).not.toBeInTheDocument();
  });

  it("fires onClose and onConfirm on the respective buttons", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(<ConfirmModal open {...base} onClose={onClose} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("disables the confirm button while pending", () => {
    render(<ConfirmModal open {...base} isPending />);
    expect(screen.getByRole("button", { name: "…" })).toBeDisabled();
  });
});
