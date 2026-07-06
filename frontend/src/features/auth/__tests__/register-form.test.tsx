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

const renderForm = () =>
  render(
    <MemoryRouter>
      <RegisterForm />
    </MemoryRouter>,
  );

describe("RegisterForm", () => {
  it("renders the three fields and the submit button", () => {
    mockFlow();
    renderForm();
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
  });

  it("submits the entered credentials", () => {
    const submit = vi.fn(() => Promise.resolve());
    mockFlow({ submit });
    renderForm();
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "hero" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "h@x.io" } });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "longpassword" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(submit).toHaveBeenCalledWith({
      username: "hero",
      email: "h@x.io",
      password: "longpassword",
    });
  });

  it("renders the error message from the flow", () => {
    mockFlow({ error: "Name already taken" });
    renderForm();
    expect(screen.getByText("Name already taken")).toBeInTheDocument();
  });
});
