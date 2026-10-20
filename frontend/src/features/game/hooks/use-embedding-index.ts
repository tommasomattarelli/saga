import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "../../../shared/stores/auth-store";
import {
  cancelEmbeddingIndex,
  getEmbeddingIndexStatus,
  retryEmbeddingIndex,
  type EmbeddingIndexStatus,
} from "../api/settings-api";

export const embeddingIndexQueryKey = (userId: string | null, campaignId: string | null) =>
  ["embedding-index", userId, campaignId] as const;

export function useEmbeddingIndexStatus(campaignId: string | null, enabled: boolean) {
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useQuery({
    queryKey: embeddingIndexQueryKey(userId, campaignId),
    queryFn: () => getEmbeddingIndexStatus(campaignId!).then((r) => r.data),
    enabled: enabled && isAuthenticated && !!userId && !!campaignId,
  });
}

export interface ScopedIndexAction {
  scopeUserId: string | null;
  scopeCampaignId: string | null;
}

export function useEmbeddingIndexActions() {
  const queryClient = useQueryClient();

  const retry = useMutation({
    mutationFn: ({ scopeCampaignId }: ScopedIndexAction) =>
      retryEmbeddingIndex(scopeCampaignId!).then((r) => r.data),
    onSuccess: (data: EmbeddingIndexStatus, variables: ScopedIndexAction) => {
      queryClient.setQueryData(
        embeddingIndexQueryKey(variables.scopeUserId, variables.scopeCampaignId),
        data,
      );
    },
  });

  const cancel = useMutation({
    mutationFn: ({ scopeCampaignId }: ScopedIndexAction) =>
      cancelEmbeddingIndex(scopeCampaignId!).then((r) => r.data),
    onSuccess: (data: EmbeddingIndexStatus, variables: ScopedIndexAction) => {
      queryClient.setQueryData(
        embeddingIndexQueryKey(variables.scopeUserId, variables.scopeCampaignId),
        data,
      );
    },
  });

  return { retry, cancel };
}
