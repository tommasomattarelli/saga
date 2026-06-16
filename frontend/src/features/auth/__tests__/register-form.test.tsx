import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

vi.mock("../hooks/use-auth-flow", () => ({ useAuthFlow: vi.fn() }));
import RegisterForm from "../components/register-form";
import { useAuthFlow } from "../hooks/use-auth-flow";

const mockFlow = (over: Partial<ReturnType<typeof useAuthFlow>> = {}) =>
  vi.mocked(useAuthFlow).mockReturnValue({
    submit: vi.fn(() => Promise.resolve()),
    isPending: false,
    error: null,
    ...over,
  });

const renderForm = () => render(<MemoryRouter><RegisterForm /></MemoryRouter>);

describe("RegisterForm", () => {
  it("renders the three fields and the submit button", () => {
    mockFlow();
    renderForm();
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(screen.getByLabelText("Sigil (email)")).toBeInTheDocument();
    expect(screen.getByLabelText("Word of Passage")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Begin Thy Tale" })).toBeInTheDocument();
  });

  it("submits the entered credentials", () => {
    const submit = vi.fn(() => Promise.resolve());
    mockFlow({ submit });
    renderForm();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "hero" } });
    fireEvent.change(screen.getByLabelText("Sigil (email)"), { target: { value: "h@x.io" } });
    fireEvent.change(screen.getByLabelText("Word of Passage"), { target: { value: "longpassword" } });
    fireEvent.click(screen.getByRole("button", { name: "Begin Thy Tale" }));
    expect(submit).toHaveBeenCalledWith({ username: "hero", email: "h@x.io", password: "longpassword" });
  });

  it("renders the error message from the flow", () => {
    mockFlow({ error: "Name already taken" });
    renderForm();
    expect(screen.getByText("Name already taken")).toBeInTheDocument();
  });
});
