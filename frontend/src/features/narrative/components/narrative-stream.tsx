import { Fragment, useLayoutEffect } from "react";
import { motion } from "framer-motion";
import { useGameStore } from "../../../shared/stores/game-store";
import { OrnamentDivider, turnDividerVariant } from "../../../shared/ui/ornament-divider";
import { OrnateFrame } from "../../../shared/ui/ornate-frame";
import { InitialSeal } from "../../../assets/ornaments/seal";
import DiceRoller from "./dice-roller";
import NPCBubble from "./npc-bubble";
import DmLoading from "./dm-loading";
import Typewriter from "./typewriter";
import type { DiceResult, NarrationSegment, TurnResponse } from "../../../shared/types";

/* Cartiglio rientrato a destra — OrnateFrame small con sigillo iniziale PG + azione */
function PlayerAction({ action }: { action: string }) {
  const heroName = useGameStore((s) => s.campaign?.character_data?.name ?? "Hero");

  return (
    <div className="my-5 ml-auto max-w-[50ch]">
      <OrnateFrame variant="small" color="var(--gold-deep)">
        <div
          className="px-1 py-1"
          style={{ background: "var(--parchment-shadow)" }}
        >
          {/* Header: sigillo + "{name} acts:" */}
          <div className="flex items-center gap-2 mb-2">
            <InitialSeal name={heroName} size={24} />
            <span
              className="font-display text-[9px] uppercase"
              style={{ color: "var(--gold-deep)", letterSpacing: "0.2em" }}
            >
              {heroName} acts:
            </span>
          </div>
          <p className="font-body italic text-lg" style={{ color: "var(--ink-primary)" }}>
            {action}
          </p>
        </div>
      </OrnateFrame>
    </div>
  );
}

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
          <p key={i} className="mb-3 leading-relaxed">
            {isFirst && paragraph.length > 0 && (
              <span
                className="float-left mr-2 font-display leading-none"
                style={{
                  fontSize: "3.2rem",
                  color: "var(--gold-bright)",
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
}: {
  segment: NarrationSegment;
  diceResults?: DiceResult[] | null;
  alwaysRevealed: boolean;
  useTypewriter: boolean;
  isFirstTurn: boolean;
}) {
  const stepDice = diceResults?.find((d) => d.step === segment.step)?.rolls ?? segment.dice;

  return (
    <Fragment>
      <div
        className="font-body text-base"
        style={{ color: "var(--ink-primary)" }}
      >
        <DmParagraphs
          text={segment.text}
          useTypewriter={useTypewriter}
          dropCap={isFirstTurn && segment.step === 1}
        />
      </div>
      {segment.npc_dialogues?.map((npc, i) => (
        <NPCBubble key={`npc-${segment.step}-${i}`} {...npc} />
      ))}
      {stepDice && <DiceRoller rolls={stepDice} alwaysRevealed={alwaysRevealed} />}
    </Fragment>
  );
}

const staggerChild = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0 },
};

function TurnBlock({
  turn,
  isLatest,
  isFresh,
  isFirst,
  showDivider,
}: {
  turn: TurnResponse;
  isLatest: boolean;
  isFresh: boolean;
  isFirst: boolean;
  showDivider: boolean;
}) {
  const segments =
    turn.narration_segments && turn.narration_segments.length > 0
      ? turn.narration_segments
      : null;

  const alwaysRevealed = !isLatest;
  const useTypewriter = isLatest && isFresh;

  return (
    <motion.div
      className="mb-6"
      data-mood={turn.scene_mood || "neutral"}
      variants={staggerChild}
      initial="hidden"
      animate="visible"
      transition={{ duration: 0.5, ease: "easeOut" }}
    >
      {showDivider && (
        <OrnamentDivider
          variant={turnDividerVariant(turn.turn_number)}
          className="!my-6"
        />
      )}

      {turn.player_action && <PlayerAction action={turn.player_action} />}

      {segments ? (
        segments.map((seg) => (
          <SegmentView
            key={seg.step}
            segment={seg}
            diceResults={turn.dice_results}
            alwaysRevealed={alwaysRevealed}
            useTypewriter={useTypewriter}
            isFirstTurn={isFirst}
          />
        ))
      ) : (
        <>
          <div
            className="font-body text-base"
            style={{ color: "var(--ink-primary)" }}
          >
            <DmParagraphs
              text={turn.narration}
              useTypewriter={useTypewriter}
              dropCap={isFirst}
            />
          </div>
          {turn.dice_rolls && (
            <DiceRoller rolls={turn.dice_rolls} alwaysRevealed={alwaysRevealed} />
          )}
        </>
      )}

      {turn.scene_mood && turn.scene_mood !== "neutral" && (
        <div
          className="mt-3 font-display text-[9px] uppercase text-center"
          style={{
            color: "var(--ink-faded)",
            letterSpacing: "0.3em",
          }}
        >
          — {turn.scene_mood.replace(/_/g, " ")} —
        </div>
      )}
    </motion.div>
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

  useLayoutEffect(() => {
    const el = scrollRef?.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turnHistory.length, isLoading, scrollRef]);

  return (
    <div aria-live="polite" aria-label="Narrative">
      {turnHistory.length === 0 && !isLoading && !pendingAction && (
        <div className="py-16 text-center">
          <p
            className="font-display text-xl uppercase"
            style={{ color: "var(--gold-bright)", letterSpacing: "0.25em" }}
          >
            Thy adventure awaits…
          </p>
          <p
            className="mt-3 font-body italic text-sm"
            style={{ color: "var(--ink-faded)" }}
          >
            Inscribe thine action below to begin
          </p>
        </div>
      )}

      {turnHistory.map((turn, i) => (
        <TurnBlock
          key={turn.turn_number}
          turn={turn}
          isLatest={i === turnHistory.length - 1}
          isFresh={turn.turn_number === freshTurnNumber}
          isFirst={i === 0}
          showDivider={i > 0}
        />
      ))}

      {pendingAction && isLoading && <PlayerAction action={pendingAction} />}

      {isLoading && <DmLoading />}

      {actionError && !isLoading && (
        <div
          className="mb-4 p-3 font-body text-sm italic"
          style={{
            border: "1px solid var(--blood)",
            background: "rgba(139, 0, 0, 0.08)",
            color: "var(--blood)",
          }}
        >
          ❧ {actionError}
        </div>
      )}
    </div>
  );
}
