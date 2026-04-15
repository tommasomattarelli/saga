import { useMutation } from "@tanstack/react-query";
import { useRef } from "react";
import { submitAction } from "../../../shared/api/client";
import { useGameStore } from "../../../shared/stores/game-store";
import { TurnResponseSchema } from "../../../shared/schemas/turn";
import type { CombatState, TurnResponse } from "../../../shared/types";

export function useSubmitAction(campaignId: string) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const addTurn = useGameStore((s) => s.addTurn);
  const setLoading = useGameStore((s) => s.setLoading);
  const setPendingAction = useGameStore((s) => s.setPendingAction);
  const setCurrentMood = useGameStore((s) => s.setCurrentMood);
  const setCombatState = useGameStore((s) => s.setCombatState);
  const updateWorldState = useGameStore((s) => s.updateWorldState);
  const updateCharacter = useGameStore((s) => s.updateCharacter);
  const updateTurnNumber = useGameStore((s) => s.updateTurnNumber);

  const mutation = useMutation({
    mutationFn: (action: string) => submitAction(campaignId, action).then((r) => r.data),
    onMutate: (action: string) => {
      setLoading(true);
      setPendingAction(action);
      requestAnimationFrame(() => {
        if (scrollRef.current)
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      });
    },
    onSuccess: (raw) => {
      const result = TurnResponseSchema.safeParse(raw);
      const turn: TurnResponse = result.success ? (result.data as unknown as TurnResponse) : raw;

      addTurn(turn);
      if (turn.world_state) updateWorldState(turn.world_state as Parameters<typeof updateWorldState>[0]);
      if (turn.character_data) updateCharacter(turn.character_data as Parameters<typeof updateCharacter>[0]);
      if (turn.turn_number) updateTurnNumber(turn.turn_number);
      if (turn.scene_mood) setCurrentMood(turn.scene_mood);

      if (turn.combat_state?.active) {
        setCombatState(turn.combat_state as CombatState);
      } else if (turn.combat_state && !turn.combat_state.active) {
        setCombatState(null);
      }
    },
    onSettled: () => {
      setLoading(false);
      setPendingAction(null);
    },
  });

  return { mutation, scrollRef };
}
