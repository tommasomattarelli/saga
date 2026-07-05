import { Fragment, useLayoutEffect, useCallback, useState, useMemo } from "react";
import { motion } from "framer-motion";
import DiceRoller from "./dice-roller";
import NPCBubble from "./npc-bubble";
import Typewriter from "./typewriter";
import PlayerAction from "./player-action";
import type { DiceResult, NarrationSegment, TurnResponse } from "../../../shared/types";

function DmParagraphs({
  text,
  useTypewriter,
  dropCap,
}: {
  text: string;
  useTypewriter: boolean;
  dropCap: boolean;
}) {
  if (useTypewriter) {
    return <Typewriter text={text} dropCap={dropCap} />;
  }
  const paragraphs = text.split("\n").filter((p) => p.length > 0);
  return (
    <>
      {paragraphs.map((paragraph, i) => {
        const isFirst = i === 0 && dropCap;
        return (
          <p key={i} className="mb-4" style={{ lineHeight: 1.62 }}>
            {isFirst && paragraph.length > 0 && (
              <span
                className="float-left mr-2 font-body leading-none"
                style={{
                  fontSize: "3.2rem",
                  color: "var(--accent)",
                  lineHeight: 0.8,
                  marginTop: "0.1em",
                }}
              >
                {paragraph[0]}
              </span>
            )}
            {isFirst ? paragraph.slice(1) : paragraph}
          </p>
        );
      })}
    </>
  );
}

function SegmentView({
  segment,
  diceResults,
  alwaysRevealed,
  useTypewriter,
  isFirstTurn,
  onDiceRevealed,
}: {
  segment: NarrationSegment;
  diceResults?: DiceResult[] | null;
  alwaysRevealed: boolean;
  useTypewriter: boolean;
  isFirstTurn: boolean;
  onDiceRevealed?: (step: number) => void;
}) {
  const stepDice = diceResults?.find((d) => d.step === segment.step)?.rolls ?? segment.dice;

  return (
    <Fragment>
      <div className="font-body text-lg" style={{ color: "var(--ink-primary)" }}>
        <DmParagraphs
          text={segment.text}
          useTypewriter={useTypewriter}
          dropCap={isFirstTurn && segment.step === 1}
        />
      </div>
      {segment.npc_dialogues?.map((npc, i) => (
        <NPCBubble key={`npc-${segment.step}-${i}`} {...npc} />
      ))}
      {stepDice && (
        <DiceRoller
          rolls={stepDice}
          alwaysRevealed={alwaysRevealed}
          step={segment.step}
          onAllRevealed={alwaysRevealed ? undefined : onDiceRevealed}
        />
      )}
    </Fragment>
  );
}

const staggerChild = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0 },
};

export default function TurnBlock({
  turn,
  isLatest,
  isFresh,
  isFirst,
  showDivider,
  onAllDiceRevealed,
}: {
  turn: TurnResponse;
  isLatest: boolean;
  isFresh: boolean;
  isFirst: boolean;
  showDivider: boolean;
  onAllDiceRevealed?: () => void;
}) {
  const segments =
    turn.narration_segments && turn.narration_segments.length > 0 ? turn.narration_segments : null;

  const alwaysRevealed = !isLatest;

  // Track which segment steps have had their dice revealed (latest turn only)
  const [revealedSteps, setRevealedSteps] = useState<ReadonlySet<number>>(new Set());

  const handleDiceRevealed = useCallback((step: number) => {
    setRevealedSteps((prev) => {
      const next = new Set(prev);
      next.add(step);
      return next;
    });
  }, []);

  // Steps that have dice in this turn
  const diceSegmentSteps = useMemo(
    () =>
      new Set(
        (segments ?? [])
          .filter((s) => !!(turn.dice_results?.find((d) => d.step === s.step)?.rolls ?? s.dice))
          .map((s) => s.step),
      ),
    [segments, turn.dice_results],
  );

  // Notify parent when all dice in this turn are revealed
  useLayoutEffect(() => {
    if (
      !alwaysRevealed &&
      diceSegmentSteps.size > 0 &&
      revealedSteps.size >= diceSegmentSteps.size
    ) {
      onAllDiceRevealed?.();
    }
  }, [revealedSteps.size, diceSegmentSteps.size, alwaysRevealed, onAllDiceRevealed]);

  // Progressive reveal: stop at first segment whose dice hasn't been clicked yet
  const visibleSegments = useMemo(() => {
    if (alwaysRevealed || !segments) return segments;
    const visible: typeof segments = [];
    for (const seg of segments) {
      visible.push(seg);
      const stepDice = turn.dice_results?.find((d) => d.step === seg.step)?.rolls ?? seg.dice;
      if (stepDice && !revealedSteps.has(seg.step)) break;
    }
    return visible;
  }, [alwaysRevealed, segments, revealedSteps, turn.dice_results]);

  return (
    <motion.div
      className="mb-6"
      variants={staggerChild}
      initial="hidden"
      animate="visible"
      transition={{ duration: 0.5, ease: "easeOut" }}
    >
      {showDivider && (
        <div className="my-8 flex items-center gap-4" role="separator" aria-hidden="true">
          <span className="h-px flex-1" style={{ background: "var(--line)" }} />
          <span className="font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
            {turn.turn_number}
          </span>
          <span className="h-px flex-1" style={{ background: "var(--line)" }} />
        </div>
      )}

      {turn.player_action && <PlayerAction action={turn.player_action} />}

      {visibleSegments ? (
        visibleSegments.map((seg) => {
          const useTypewriter = isLatest && isFresh;
          return (
            <SegmentView
              key={seg.step}
              segment={seg}
              diceResults={turn.dice_results}
              alwaysRevealed={alwaysRevealed}
              useTypewriter={useTypewriter}
              isFirstTurn={isFirst}
              onDiceRevealed={handleDiceRevealed}
            />
          );
        })
      ) : (
        <>
          <div className="font-body text-lg" style={{ color: "var(--ink-primary)" }}>
            <DmParagraphs
              text={turn.narration}
              useTypewriter={isLatest && isFresh}
              dropCap={isFirst}
            />
          </div>
          {turn.dice_rolls && (
            <DiceRoller
              rolls={turn.dice_rolls}
              alwaysRevealed={alwaysRevealed}
              onAllRevealed={alwaysRevealed ? undefined : () => onAllDiceRevealed?.()}
            />
          )}
        </>
      )}
    </motion.div>
  );
}
