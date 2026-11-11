import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { RefObject } from "react";
import { getRuntimeConfig, submitAction } from "../../../shared/api/client";
import { useGameStore } from "../../../shared/stores/game-store";
import {
  ActionResponseIdentitySchema,
  RuntimeConfigSchema,
  TurnResponseSchema,
} from "../../../shared/schemas/turn";
import type { TurnResponse } from "../../../shared/types";

export function useSubmitAction(campaignId: string, scrollRef: RefObject<HTMLDivElement | null>) {
  const queryClient = useQueryClient();
  const config = useQuery({
    queryKey: ["runtime-config"],
    queryFn: async () => RuntimeConfigSchema.parse((await getRuntimeConfig()).data),
  });
  const mutation = useMutation({
    mutationFn: async ({
      action,
      requestId,
      expectedContext,
    }: {
      action: string;
      requestId: string;
      expectedContext?: { head: string | null; epoch: number };
    }) => {
      const campaign = useGameStore.getState().campaign;
      if (!config.data || !campaign || campaign.id !== campaignId)
        throw new Error("action_not_ready");
      const context = {
        campaignId,
        head: expectedContext ? expectedContext.head : (campaign.active_head_turn_id ?? null),
        epoch: expectedContext ? expectedContext.epoch : (campaign.context_epoch ?? 0),
      };
      const response = await submitAction(
        campaignId,
        {
          action,
          request_id: requestId,
          expected_head_turn_id: context.head,
          expected_context_epoch: context.epoch,
        },
        config.data.action_client_timeout_seconds * 1000,
      );
      const identity = ActionResponseIdentitySchema.parse(response.data);
      if (
        identity.request_id !== requestId ||
        identity.context_epoch !== context.epoch ||
        identity.head_turn_id !== identity.turn_id
      ) {
        throw new Error("action_response_identity_mismatch");
      }
      return { turn: response.data, context };
    },

    onMutate: ({
      action,
    }: {
      action: string;
      requestId: string;
      expectedContext?: { head: string | null; epoch: number };
    }) => {
      const { setLoading, setPendingAction } = useGameStore.getState();
      setLoading(true);
      setPendingAction(action);
      const el = scrollRef.current;
      requestAnimationFrame(() => {
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    onSuccess: async ({
      turn,
      context,
    }: {
      turn: TurnResponse;
      context: { campaignId: string; head: string | null; epoch: number };
    }) => {
      if (import.meta.env.DEV) {
        const check = TurnResponseSchema.safeParse(turn);
        if (!check.success) console.warn("[useSubmitAction] schema mismatch", check.error.issues);
      }

      if (
        turn.turn_id &&
        useGameStore.getState().turnHistory.some((item) => item.turn_id === turn.turn_id)
      ) {
        return;
      }
      const current = useGameStore.getState().campaign;
      if (
        current?.id === context.campaignId &&
        (current.active_head_turn_id ?? null) === context.head &&
        (current.context_epoch ?? 0) === context.epoch
      ) {
        useGameStore.getState().applyTurn(turn);
      } else if (
        current?.id !== context.campaignId ||
        (current.active_head_turn_id ?? null) !== context.head ||
        (current.context_epoch ?? 0) !== context.epoch
      ) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["campaign", context.campaignId] }),
          queryClient.invalidateQueries({ queryKey: ["turns", context.campaignId] }),
        ]);
        return;
      }
    },

    onError: async (error) => {
      if (isContextChanged(error)) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["campaign", campaignId] }),
          queryClient.invalidateQueries({ queryKey: ["turns", campaignId] }),
        ]);
      }
    },

    onSettled: () => {
      const { setLoading, setPendingAction } = useGameStore.getState();
      setLoading(false);
      setPendingAction(null);
    },
  });

  const submit = (
    action: string,
    requestId: string = crypto.randomUUID(),
    expectedContext?: { head: string | null; epoch: number },
  ) => mutation.mutateAsync({ action, requestId, expectedContext });
  return { mutation, submit, actionReady: config.isSuccess };
}

function isContextChanged(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof error.response === "object" &&
    error.response !== null &&
    "data" in error.response &&
    typeof error.response.data === "object" &&
    error.response.data !== null &&
    "detail" in error.response.data &&
    typeof error.response.data.detail === "object" &&
    error.response.data.detail !== null &&
    "code" in error.response.data.detail &&
    error.response.data.detail.code === "action_context_changed"
  );
}
