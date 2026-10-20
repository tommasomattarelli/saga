import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  classifySettingsError,
  putApiKeys,
  type ApiKeysUpdate,
  type KeyProvider,
  type SettingsErrorKind,
} from "../api/settings-api";
import { settingsQueryKey } from "./use-ai-settings";
import { useAuthStore } from "../../../shared/stores/auth-store";

/* The key never becomes state, a mutation variable or a cache entry: it is
   handed to the request and dropped. Only a coarse error kind is kept. */
export function useApiKeySaver() {
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const queryClient = useQueryClient();
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<SettingsErrorKind | null>(null);

  const save = useCallback(
    async (provider: KeyProvider, key: string): Promise<boolean> => {
      setIsSaving(true);
      setError(null);
      const scopeUserId = userId;
      const payload: ApiKeysUpdate = {};
      payload[provider] = key;
      try {
        await putApiKeys(payload);
        await queryClient.invalidateQueries({ queryKey: settingsQueryKey(scopeUserId) });
        return true;
      } catch (err) {
        if (useAuthStore.getState().user?.id === scopeUserId) {
          setError(classifySettingsError(err));
        }
        return false;
      } finally {
        setIsSaving(false);
      }
    },
    [queryClient, userId],
  );

  return { save, isSaving, error };
}
