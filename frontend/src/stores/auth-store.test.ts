import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "./auth-store";

describe("Auth Store", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
  });

  it("should initialize with default values", () => {
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.accessToken).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it("should store tokens and set isAuthenticated to true", () => {
    const { setTokens } = useAuthStore.getState();
    setTokens({ access_token: "access123", refresh_token: "refresh456", token_type: "bearer" });

    const state = useAuthStore.getState();
    expect(state.accessToken).toBe("access123");
    expect(state.refreshToken).toBe("refresh456");
    expect(state.isAuthenticated).toBe(true);
  });

  it("should set user correctly", () => {
    const { setUser } = useAuthStore.getState();
    const user = { id: "1", username: "test", email: "test@test.com", preferred_language: "en" };
    setUser(user);
    expect(useAuthStore.getState().user).toEqual(user);
  });

  it("should logout correctly by clearing tokens", () => {
    const { setTokens, logout } = useAuthStore.getState();
    setTokens({ access_token: "access123", refresh_token: "refresh456", token_type: "bearer" });

    logout();

    const state = useAuthStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
  });
});
