import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { getCampaign, getTurns } from "../../../shared/api/client";
import { useGameStore } from "../../../shared/stores/game-store";
import type { TurnResponse } from "../../../shared/types";

export function useCampaignData(campaignId: string | undefined) {
  const setCampaign = useGameStore((s) => s.setCampaign);
  const setTurnHistory = useGameStore((s) => s.setTurnHistory);

  const campaignQuery = useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () => getCampaign(campaignId!).then((r) => r.data),
    enabled: !!campaignId,
  });

  const turnsQuery = useQuery({
    queryKey: ["turns", campaignId],
    queryFn: () => getTurns(campaignId!).then((r) => r.data),
    enabled: !!campaignId,
  });

  useEffect(() => {
    if (!campaignQuery.data) return;
    setCampaign(campaignQuery.data);
  }, [campaignQuery.data, setCampaign]);

  useEffect(() => {
    if (!turnsQuery.data?.length) return;
    setTurnHistory([...turnsQuery.data].reverse() as TurnResponse[]);
  }, [turnsQuery.data, setTurnHistory]);

  return {
    isLoading: campaignQuery.isLoading || turnsQuery.isLoading,
    error: campaignQuery.error ?? turnsQuery.error,
  };
}
