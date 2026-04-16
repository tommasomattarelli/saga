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

/* Moods that get the SVG fog treatment */
const FOG_MOODS = new Set(["wonder_discovery", "dread_horror", "stealth_danger", "melancholic_reflection"]);

/* Individual drifting fog ellipse */
function FogEllipse({
  cx, cy, rx, ry, dur, delay, color,
}: {
  cx: number; cy: number; rx: number; ry: number;
  dur: number; delay: number; color: string;
}) {
  return (
    <motion.ellipse
      cx={`${cx}%`} cy={`${cy}%`} rx={`${rx}%`} ry={`${ry}%`}
      fill={color}
      initial={{ opacity: 0, x: 0, y: 0 }}
      animate={{
        opacity: [0, 0.18, 0.10, 0.20, 0],
        x: [0, 18, -12, 20, 0],
        y: [0, -10, 8, -6, 0],
      }}
      transition={{
        duration: dur,
        delay,
        repeat: Infinity,
        ease: "easeInOut",
      }}
    />
  );
}

function FogLayer({ mood }: { mood: string }) {
  const isDread = mood === "dread_horror";
  const color = isDread ? "rgba(40,0,40,0.55)" : "rgba(180,180,210,0.22)";

  return (
    <svg
      aria-hidden="true"
      style={{ position: "fixed", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 3 }}
    >
      <FogEllipse cx={20} cy={60} rx={35} ry={18} dur={28} delay={0}    color={color} />
      <FogEllipse cx={65} cy={75} rx={42} ry={22} dur={34} delay={6}    color={color} />
      <FogEllipse cx={45} cy={40} rx={28} ry={14} dur={22} delay={12}   color={color} />
      <FogEllipse cx={80} cy={50} rx={30} ry={16} dur={30} delay={4}    color={color} />
      <FogEllipse cx={10} cy={30} rx={25} ry={12} dur={26} delay={18}   color={color} />
    </svg>
  );
}

export function MoodLayer() {
  const mood = useGameStore((s) => s.currentMood);
  const overlay = MOOD_OVERLAYS[mood] ?? MOOD_OVERLAYS["neutral"];
  const hasFog = FOG_MOODS.has(mood);

  return (
    <>
      {/* CSS gradient overlay */}
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

      {/* SVG fog layer for atmospheric moods */}
      <AnimatePresence>
        {hasFog && (
          <motion.div
            key={`fog-${mood}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 2.5, ease: "easeInOut" }}
            style={{ position: "fixed", inset: 0, zIndex: 3, pointerEvents: "none" }}
          >
            <FogLayer mood={mood} />
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
