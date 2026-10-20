import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "../../../shared/stores/auth-store";
import {
  getSettings,
  patchSettings,
  putServerKeyConsents,
  type ProfilePatch,
  type SettingsResponse,
} from "../api/settings-api";

export const settingsQueryKey = (userId: string | null) => ["settings", userId] as const;

export function useAiSettings(enabled: boolean) {
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useQuery({
    queryKey: settingsQueryKey(userId),
    queryFn: () => getSettings().then((r) => r.data),
    enabled: enabled && isAuthenticated && !!userId,
  });
}

/* The scope travels with the request: React Query refreshes the callbacks of a
   pending mutation on every render, so the scope is captured at submit time —
   a late answer writes back under the user who sent it, never under whoever
   is signed in when it lands. */
export interface ScopedProfileSave {
  patch: ProfilePatch;
  scopeUserId: string | null;
}

export function useSaveProfiles() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ patch }: ScopedProfileSave) => patchSettings(patch).then((r) => r.data),
    onSuccess: (data: SettingsResponse, variables: ScopedProfileSave) => {
      queryClient.setQueryData(settingsQueryKey(variables.scopeUserId), data);
    },
  });
}

export interface ScopedConsentSave {
  provider: string;
  enabled: boolean;
  scopeUserId: string | null;
}

export function useSaveConsent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ provider, enabled }: ScopedConsentSave) =>
      putServerKeyConsents({ [provider]: enabled }).then((r) => r.data.server_key_consents),
    onSuccess: async (consents: Record<string, boolean>, variables: ScopedConsentSave) => {
      const key = settingsQueryKey(variables.scopeUserId);
      queryClient.setQueryData<SettingsResponse>(key, (previous) =>
        previous ? { ...previous, server_key_consents: consents } : previous,
      );
      /* The credential provenance follows the consents: reload it. */
      await queryClient.invalidateQueries({ queryKey: key });
    },
  });
}
