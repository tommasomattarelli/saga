import { AnimatePresence, motion } from "framer-motion";
import { useGameStore } from "../stores/game-store";

type MoodOverlay = {
  background: string;
  opacity: number;
};

const MOOD_OVERLAYS: Record<string, MoodOverlay> = {
  tense_anticipation: {
    background: "radial-gradient(ellipse at center, transparent 30%, rgba(0,0,0,0.6) 100%)",
    opacity: 1,
  },
  combat_fury: {
    background:
      "radial-gradient(ellipse at 50% 100%, rgba(139,0,0,0.25) 0%, transparent 70%), radial-gradient(ellipse at center, transparent 50%, rgba(139,0,0,0.15) 100%)",
    opacity: 1,
  },
  dread_horror: {
    background:
      "radial-gradient(ellipse at center, transparent 20%, rgba(10,0,10,0.7) 100%)",
    opacity: 1,
  },
  stealth_danger: {
    background:
      "linear-gradient(to bottom, rgba(15,15,35,0.4) 0%, transparent 40%, rgba(15,15,35,0.4) 100%)",
    opacity: 1,
  },
  calm_exploration: {
    background:
      "radial-gradient(ellipse at 20% 10%, rgba(212,175,55,0.12) 0%, transparent 50%)",
    opacity: 1,
  },
  triumphant_victory: {
    background:
      "radial-gradient(ellipse at 50% 0%, rgba(212,175,55,0.2) 0%, transparent 60%)",
    opacity: 1,
  },
  wonder_discovery: {
    background:
      "radial-gradient(ellipse at 50% 50%, rgba(30,58,95,0.2) 0%, transparent 70%)",
    opacity: 1,
  },
  social_intrigue: {
    background:
      "radial-gradient(ellipse at 80% 20%, rgba(168,85,247,0.08) 0%, transparent 50%)",
    opacity: 1,
  },
  melancholic_reflection: {
    background:
      "linear-gradient(to bottom, rgba(30,30,50,0.3) 0%, transparent 60%)",
    opacity: 1,
  },
  mourning_loss: {
    background: "linear-gradient(to bottom, rgba(0,0,0,0.4) 0%, transparent 80%)",
    opacity: 1,
  },
  neutral: { background: "transparent", opacity: 0 },
};

export function MoodLayer() {
  const mood = useGameStore((s) => s.currentMood);
  const overlay = MOOD_OVERLAYS[mood] ?? MOOD_OVERLAYS["neutral"];

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={mood}
        aria-hidden="true"
        initial={{ opacity: 0 }}
        animate={{ opacity: overlay.opacity }}
        exit={{ opacity: 0 }}
        transition={{ duration: 1.8, ease: "easeInOut" }}
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 2,
          pointerEvents: "none",
          background: overlay.background,
        }}
      />
    </AnimatePresence>
  );
}
