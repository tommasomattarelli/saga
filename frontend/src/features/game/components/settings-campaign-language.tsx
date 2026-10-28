import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { updateCampaignLanguage } from "../../../shared/api/client";
import { useGameStore } from "../../../shared/stores/game-store";
import type { Campaign } from "../../../shared/types";
import LanguageSelect from "../../campaign/components/language-select";

export default function SettingsCampaignLanguage() {
  const { t } = useTranslation();
  const campaign = useGameStore((state) => state.campaign);
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ id, language }: { id: string; language: string }) =>
      updateCampaignLanguage(id, language),
    onSuccess: (response) => {
      const current = useGameStore.getState().campaign;
      if (current?.id === response.data.id) {
        useGameStore.getState().setCampaign({ ...current, language: response.data.language });
      }
      void queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      queryClient.setQueryData<Campaign>(["campaign", response.data.id], (cached) =>
        cached ? { ...cached, language: response.data.language } : undefined,
      );
    },
  });
  if (!campaign) return null;

  return (
    <section className="mb-4">
      <LanguageSelect
        value={campaign.language}
        disabled={mutation.isPending}
        onChange={(language) => mutation.mutate({ id: campaign.id, language })}
      />
      {mutation.isError && (
        <p role="alert" className="mt-2 font-display text-xs" style={{ color: "var(--blood)" }}>
          {t("campaign.language_save_error")}
        </p>
      )}
    </section>
  );
}
