import { Fragment, useLayoutEffect } from "react";
import { useGameStore } from "../../stores/game-store";
import DiceRoller from "./dice-roller";
import NPCBubble from "./npc-bubble";
import DmLoading from "./dm-loading";
import Typewriter from "./typewriter";
import type { DiceResult, NarrationSegment, TurnResponse } from "../../types";

function PlayerBubble({ action }: { action: string }) {
  return (
    <div className="mb-4 flex justify-end">
      <div className="max-w-[80%] rounded-lg border border-gold-500/20 bg-gold-900/30 px-4 py-2">
        <p className="text-sm font-serif text-gold-300">{action}</p>
      </div>
    </div>
  );
}

function SegmentView({
  segment,
  diceResults,
  alwaysRevealed,
  useTypewriter,
}: {
  segment: NarrationSegment;
  diceResults?: DiceResult[] | null;
  alwaysRevealed: boolean;
  useTypewriter: boolean;
}) {
  // Find dice for this step from dice_results array
  const stepDice = diceResults?.find((d) => d.step === segment.step)?.rolls ?? segment.dice;

  return (
    <Fragment>
      <div className="prose prose-invert max-w-none font-serif leading-relaxed mood-text">
        {useTypewriter ? (
          <Typewriter text={segment.text} />
        ) : (
          segment.text.split("\n").map((paragraph, i) => (
            <p key={i} className="mb-3">
              {paragraph}
            </p>
          ))
        )}
      </div>
      {segment.npc_dialogues?.map((npc, i) => (
        <NPCBubble key={`npc-${segment.step}-${i}`} {...npc} />
      ))}
      {stepDice && <DiceRoller rolls={stepDice} alwaysRevealed={alwaysRevealed} />}
    </Fragment>
  );
}

function TurnBlock({
  turn,
  isLatest,
  isFresh,
}: {
  turn: TurnResponse;
  isLatest: boolean;
  isFresh: boolean;
}) {
  const segments =
    turn.narration_segments && turn.narration_segments.length > 0
      ? turn.narration_segments
      : null;

  // Historical turns: always revealed dice, no typewriter
  // Latest turn that was submitted in this session: typewriter effect + clickable dice
  const alwaysRevealed = !isLatest;
  const useTypewriter = isLatest && isFresh;

  return (
    <div className="mb-6" data-mood={turn.scene_mood || "neutral"}>
      {turn.player_action && <PlayerBubble action={turn.player_action} />}

      {segments ? (
        segments.map((seg) => (
          <SegmentView
            key={seg.step}
            segment={seg}
            diceResults={turn.dice_results}
            alwaysRevealed={alwaysRevealed}
            useTypewriter={useTypewriter}
          />
        ))
      ) : (
        <>
          <div className="prose prose-invert max-w-none font-serif leading-relaxed mood-text">
            {useTypewriter ? (
              <Typewriter text={turn.narration} />
            ) : (
              turn.narration.split("\n").map((paragraph, i) => (
                <p key={i} className="mb-3">
                  {paragraph}
                </p>
              ))
            )}
          </div>
          {turn.dice_rolls && (
            <DiceRoller rolls={turn.dice_rolls} alwaysRevealed={alwaysRevealed} />
          )}
        </>
      )}

      {turn.scene_mood && turn.scene_mood !== "neutral" && (
        <div className="mood-accent mt-2 text-xs uppercase tracking-wider">
          {turn.scene_mood.replace(/_/g, " ")}
        </div>
      )}
    </div>
  );
}

export default function NarrativeStream({
  scrollRef,
  actionError,
}: {
  scrollRef?: React.RefObject<HTMLDivElement | null>;
  actionError?: string | null;
}) {
  const turnHistory = useGameStore((s) => s.turnHistory);
  const isLoading = useGameStore((s) => s.isLoading);
  const pendingAction = useGameStore((s) => s.pendingAction);
  const freshTurnNumber = useGameStore((s) => s.freshTurnNumber);

  // Scroll to bottom on new content
  useLayoutEffect(() => {
    const el = scrollRef?.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turnHistory.length, isLoading, scrollRef]);

  return (
    <div>
      {turnHistory.length === 0 && !isLoading && !pendingAction && (
        <div className="py-12 text-center">
          <p className="font-display text-xl text-gold-400">Your adventure awaits…</p>
          <p className="mt-2 text-sm text-parchment-500">Type an action below to begin</p>
        </div>
      )}

      {turnHistory.map((turn, i) => (
        <TurnBlock
          key={turn.turn_number}
          turn={turn}
          isLatest={i === turnHistory.length - 1}
          isFresh={turn.turn_number === freshTurnNumber}
        />
      ))}

      {/* Pending player action bubble shown while loading */}
      {pendingAction && isLoading && <PlayerBubble action={pendingAction} />}

      {/* Skeleton loader while DM is thinking */}
      {isLoading && <DmLoading />}

      {/* Error feedback when the DM node fails */}
      {actionError && !isLoading && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-900/20 px-4 py-3">
          <p className="font-serif text-sm text-red-300">{actionError}</p>
        </div>
      )}
    </div>
  );
}
