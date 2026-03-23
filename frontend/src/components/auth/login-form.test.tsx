import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import LoginForm from "./login-form";
import { login, getMe } from "../../services/api";
import type { TokenPair, User } from "../../types";

vi.mock("../../services/api", () => ({
  login: vi.fn(),
  getMe: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
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
      </QueryClientProvider>,
    );

  it("should render login form", () => {
    renderComponent();
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /enter the realm/i })).toBeInTheDocument();
  });

  it("should call login and navigate on success", async () => {
    vi.mocked(login).mockResolvedValue({
      data: { access_token: "pk", refresh_token: "rk", token_type: "bearer" },
      status: 200,
      statusText: "OK",
      headers: {},
      config: {} as InternalAxiosRequestConfig,
    } as AxiosResponse<TokenPair>);

    vi.mocked(getMe).mockResolvedValue({
      data: { id: "1", username: "testuser", email: "test@test.com", preferred_language: "en" },
      status: 200,
      statusText: "OK",
      headers: {},
      config: {} as InternalAxiosRequestConfig,
    } as AxiosResponse<User>);

    renderComponent();

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "testuser" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /enter the realm/i }));

    await waitFor(() => expect(login).toHaveBeenCalledWith("testuser", "password123"), {
      timeout: 2000,
    });
    await waitFor(() => expect(getMe).toHaveBeenCalled());
    expect(mockNavigate).toHaveBeenCalledWith("/campaigns");
  });

  it("should show error on login failure", async () => {
    vi.mocked(login).mockRejectedValue(new Error("Auth failed"));

    renderComponent();

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "baduser" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "badpass" } });
    fireEvent.click(screen.getByRole("button", { name: /enter the realm/i }));

    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
  });
});
