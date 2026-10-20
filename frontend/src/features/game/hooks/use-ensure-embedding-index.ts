import { useEffect } from "react";
import { ensureCampaignEmbeddingIndex } from "../../../shared/api/client";
import { useAuthStore } from "../../../shared/stores/auth-store";

const inFlight = new Map<string, Promise<unknown>>();

export function useEnsureEmbeddingIndex(campaignId: string | undefined): void {
  const userId = useAuthStore((state) => (state.isAuthenticated ? state.user?.id : undefined));
  const sessionId = useAuthStore((state) =>
    state.isAuthenticated ? state.refreshToken : undefined,
  );

  useEffect(() => {
    if (!campaignId || !userId || !sessionId) return;
    const key = `${userId}:${sessionId}:${campaignId}`;
    if (inFlight.has(key)) return;
    const request = ensureCampaignEmbeddingIndex(campaignId).catch(() => undefined);
    inFlight.set(key, request);
    void request.finally(() => {
      if (inFlight.get(key) === request) inFlight.delete(key);
    });
  }, [campaignId, sessionId, userId]);
}
