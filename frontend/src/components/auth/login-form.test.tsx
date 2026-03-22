import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LoginForm from "./login-form";
import { login, getMe } from "../../services/api";

vi.mock("../../services/api", () => ({
  login: vi.fn(),
  getMe: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom") as any;
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    Link: actual.Link,
  };
});

describe("LoginForm Component", () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderComponent = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <LoginForm />
        </BrowserRouter>
      </QueryClientProvider>
    );

  it("should render login form", () => {
    renderComponent();
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /enter the realm/i })).toBeInTheDocument();
  });

  it("should call login and navigate on success", async () => {
    (login as any).mockResolvedValue({ 
      data: { access_token: "pk", refresh_token: "rk", token_type: "bearer" } 
    });
    (getMe as any).mockResolvedValue({
      data: { id: "1", username: "testuser" }
    });

    renderComponent();

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "testuser" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /enter the realm/i }));

    await waitFor(() => expect(login).toHaveBeenCalledWith("testuser", "password123"), { timeout: 2000 });
    await waitFor(() => expect(getMe).toHaveBeenCalled());
    expect(mockNavigate).toHaveBeenCalledWith("/campaigns");
  });

  it("should show error on login failure", async () => {
    (login as any).mockRejectedValue(new Error("Auth failed"));

    renderComponent();

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "baduser" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "badpass" } });
    fireEvent.click(screen.getByRole("button", { name: /enter the realm/i }));

    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
  });
});
