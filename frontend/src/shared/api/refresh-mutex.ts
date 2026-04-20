import axios from "axios";
import type { TokenPair } from "../types";
import { useAuthStore } from "../stores/auth-store";

let inflightRefresh: Promise<string> | null = null;

export async function refreshMutex(refreshToken: string): Promise<string> {
  if (inflightRefresh) return inflightRefresh;

  inflightRefresh = axios
    .post<TokenPair>("/api/auth/refresh", { refresh_token: refreshToken })
    .then(({ data }) => {
      useAuthStore.getState().setTokens(data);
      return data.access_token;
    })
    .finally(() => {
      inflightRefresh = null;
    });

  return inflightRefresh;
}
