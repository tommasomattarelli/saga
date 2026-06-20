import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAuthFlow } from "../use-auth-flow";
import { createWrapper } from "../../../../shared/utils/test-utils";
import * as client from "../../../../shared/api/client";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("../../../../shared/api/client", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn(),
}));

const mockLogin = vi.mocked(client.login);
const mockRegister = vi.mocked(client.register);
const mockGetMe = vi.mocked(client.getMe);

beforeEach(() => {
  vi.clearAllMocks();
  mockGetMe.mockResolvedValue({
    data: { id: "1", username: "tomma", email: "t@t.com", preferred_language: "en" },
  } as never);
});

describe("useAuthFlow — login mode", () => {
  it("sets tokens + user and navigates on success", async () => {
    mockLogin.mockResolvedValue({
      data: { access_token: "acc", refresh_token: "ref", token_type: "bearer" },
    } as never);

    const { result } = renderHook(() => useAuthFlow("login"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.submit({ username: "tomma", password: "pass" });
    });

    expect(result.current.error).toBeNull();
    expect(mockNavigate).toHaveBeenCalledWith("/campaigns");
  });

  it("classifies 401 as invalid credentials", async () => {
    mockLogin.mockRejectedValue({ response: { status: 401 } });

    const { result } = renderHook(() => useAuthFlow("login"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.submit({ username: "tomma", password: "wrong" });
    });

    expect(result.current.error).toBe("Invalid credentials.");
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("classifies 500 as server error", async () => {
    mockLogin.mockRejectedValue({ response: { status: 500 } });

    const { result } = renderHook(() => useAuthFlow("login"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.submit({ username: "tomma", password: "pass" });
    });

    expect(result.current.error).toBe("Server error. Please try again later.");
  });

  it("classifies missing response as network error", async () => {
    mockLogin.mockRejectedValue(new Error("Network Error"));

    const { result } = renderHook(() => useAuthFlow("login"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.submit({ username: "tomma", password: "pass" });
    });

    expect(result.current.error).toBe("Network error. Check your connection.");
  });

  it("sets isPending during submission", async () => {
    let resolveLogin!: () => void;
    mockLogin.mockReturnValue(
      new Promise((resolve) => {
        resolveLogin = () =>
          resolve({
            data: { access_token: "a", refresh_token: "r", token_type: "bearer" },
          } as never);
      }),
    );

    const { result } = renderHook(() => useAuthFlow("login"), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.submit({ username: "tomma", password: "pass" });
    });

    expect(result.current.isPending).toBe(true);

    await act(async () => {
      resolveLogin();
    });

    expect(result.current.isPending).toBe(false);
  });
});

describe("useAuthFlow — register mode", () => {
  it("calls register with email and navigates on success", async () => {
    mockRegister.mockResolvedValue({
      data: { access_token: "acc", refresh_token: "ref", token_type: "bearer" },
    } as never);

    const { result } = renderHook(() => useAuthFlow("register"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.submit({ username: "tomma", password: "pass", email: "t@t.com" });
    });

    expect(mockRegister).toHaveBeenCalledWith("tomma", "t@t.com", "pass");
    expect(mockNavigate).toHaveBeenCalledWith("/campaigns");
  });
});
