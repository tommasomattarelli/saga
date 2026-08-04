import { useMutation } from "@tanstack/react-query";
import type { RefObject } from "react";
import { submitAction } from "../../../shared/api/client";
import { useGameStore } from "../../../shared/stores/game-store";
import { TurnResponseSchema } from "../../../shared/schemas/turn";
import type { TurnResponse, WorldState, CharacterData } from "../../../shared/types";

export function useSubmitAction(campaignId: string, scrollRef: RefObject<HTMLDivElement | null>) {
  const mutation = useMutation({
    mutationFn: (action: string) => submitAction(campaignId, action).then((r) => r.data),

    onMutate: (action: string) => {
      const { setLoading, setPendingAction } = useGameStore.getState();
      setLoading(true);
      setPendingAction(action);
      const el = scrollRef.current;
      requestAnimationFrame(() => {
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    onSuccess: (turn: TurnResponse) => {
      if (import.meta.env.DEV) {
        const check = TurnResponseSchema.safeParse(turn);
        if (!check.success) console.warn("[useSubmitAction] schema mismatch", check.error.issues);
      }

      const { addTurn, updateWorldState, updateCharacter, updateTurnNumber } =
        useGameStore.getState();

      addTurn(turn);
      if (turn.world_state) updateWorldState(turn.world_state as Partial<WorldState>);
      if (turn.character_data) updateCharacter(turn.character_data as Partial<CharacterData>);
      if (turn.turn_number) updateTurnNumber(turn.turn_number);
    },

    onSettled: () => {
      const { setLoading, setPendingAction } = useGameStore.getState();
      setLoading(false);
      setPendingAction(null);
    },
  });

  return { mutation };
}
