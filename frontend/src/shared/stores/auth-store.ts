import { create } from "zustand";
import type { User, TokenPair } from "../types";
import { useGameStore } from "./game-store";

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  setTokens: (tokens: TokenPair) => void;
  setUser: (user: User) => void;
  logout: () => void;
}

function loadRefreshToken(): string | null {
  try {
    return sessionStorage.getItem("saga-refresh-token");
  } catch {
    return null;
  }
}

function saveRefreshToken(token: string | null): void {
  try {
    if (token) {
      sessionStorage.setItem("saga-refresh-token", token);
    } else {
      sessionStorage.removeItem("saga-refresh-token");
    }
  } catch {
    // sessionStorage unavailable (e.g. private browsing restriction) — degrade gracefully
  }
}

export const useAuthStore = create<AuthState>()((set) => ({
  user: null,
  // accessToken is memory-only: never persisted, cleared on page reload
  accessToken: null,
  // refreshToken survives tab reload via sessionStorage, not across browser closes
  refreshToken: loadRefreshToken(),
  isAuthenticated: false,
  setTokens: (tokens) => {
    saveRefreshToken(tokens.refresh_token);
    set({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      isAuthenticated: true,
    });
  },
  setUser: (user) => set({ user }),
  logout: () => {
    saveRefreshToken(null);
    useGameStore.getState().reset();
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
  },
}));
