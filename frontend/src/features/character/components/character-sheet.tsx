import * as Dialog from "@radix-ui/react-dialog";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";
import { getHP, abilityMod } from "../../../shared/utils/dnd";
import { InitialSeal } from "../../../assets/ornaments/seal";
import { OrnamentDivider } from "../../../shared/ui/ornament-divider";
import { CornerFlourish } from "../../../assets/ornaments/corner-flourish";

const ABILITY_ORDER = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"];

function StatSigil({ name, score }: { name: string; score: number }) {
  const mod = abilityMod(score);
  return (
    <div className="flex flex-col items-center">
      <svg width={72} height={72} viewBox="0 0 72 72" aria-label={`${name}: ${score}`}>
        <circle cx="36" cy="36" r="34" fill="none" stroke="var(--gold-deep)" strokeWidth="1" opacity="0.6" />
        <circle cx="36" cy="36" r="28" fill="none" stroke="var(--gold-deep)" strokeWidth="0.5" opacity="0.3" />
        {/* Stat abbrev arc top */}
        <text
          x="36" y="18"
          textAnchor="middle"
          fontSize="8"
          fill="var(--gold-deep)"
          fontFamily="var(--font-display)"
          letterSpacing="0.2em"
          style={{ textTransform: "uppercase" }}
        >
          {name.slice(0, 3)}
        </text>
        {/* Score centre */}
        <text
          x="36" y="42"
          textAnchor="middle"
          fontSize="22"
          fill="var(--gold-bright)"
          fontFamily="var(--font-display)"
        >
          {score}
        </text>
        {/* Modifier bottom */}
        <text
          x="36" y="58"
          textAnchor="middle"
          fontSize="10"
          fill="var(--ink-secondary)"
          fontFamily="var(--font-display)"
        >
          {mod}
        </text>
      </svg>
    </div>
  );
}

function HpBar({ current, max }: { current: number; max: number }) {
  const pct = max > 0 ? (current / max) * 100 : 0;
  return (
    <div className="mt-4">
      <div className="flex justify-between mb-1">
        <span className="font-display text-[10px] uppercase" style={{ color: "var(--ink-faded)", letterSpacing: "0.2em" }}>HP</span>
        <span className="font-display text-sm" style={{ color: "var(--gold-bright)" }}>{current} / {max}</span>
      </div>
      <div
        className="relative h-3 overflow-hidden"
        style={{ border: "1px solid var(--gold-deep)", background: "rgba(139, 0, 0, 0.08)" }}
      >
        <motion.div
          className="h-full"
          style={{ background: "var(--blood)" }}
          initial={false}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}

export default function CharacterSheet() {
  const campaign = useGameStore((s) => s.campaign);
  const sidePanel = useUIStore((s) => s.sidePanel);
  const setSidePanel = useUIStore((s) => s.setSidePanel);

  const open = sidePanel === "character";

  if (!campaign) return null;
  const char = campaign.character_data;
  const hp = char ? getHP(char) : null;

  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && setSidePanel(null)}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild>
              <motion.div
                className="fixed inset-0 z-40 bg-black/60"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
              />
            </Dialog.Overlay>

            <Dialog.Content asChild>
              <motion.div
                className="fixed inset-4 z-50 flex items-center justify-center"
                style={{ perspective: 2000 }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <motion.div
                  className="relative w-full max-w-5xl max-h-[90vh] overflow-hidden"
                  style={{
                    background: "var(--parchment-base)",
                    border: "1px solid var(--gold-deep)",
                    outline: "1px solid rgba(184, 134, 11, 0.2)",
                    outlineOffset: "4px",
                  }}
                  initial={{ rotateY: 90, opacity: 0 }}
                  animate={{ rotateY: 0, opacity: 1 }}
                  exit={{ rotateY: -90, opacity: 0 }}
                  transition={{ duration: 0.7, ease: [0.77, 0, 0.175, 1] }}
                >
                  {/* Corner flourishes */}
                  <span className="absolute top-0 left-0 -translate-x-1 -translate-y-1 pointer-events-none">
                    <CornerFlourish corner="tl" size={28} />
                  </span>
                  <span className="absolute top-0 right-0 translate-x-1 -translate-y-1 pointer-events-none">
                    <CornerFlourish corner="tr" size={28} />
                  </span>
                  <span className="absolute bottom-0 left-0 -translate-x-1 translate-y-1 pointer-events-none">
                    <CornerFlourish corner="bl" size={28} />
                  </span>
                  <span className="absolute bottom-0 right-0 translate-x-1 translate-y-1 pointer-events-none">
                    <CornerFlourish corner="br" size={28} />
                  </span>

                  {/* Close */}
                  <Dialog.Close
                    aria-label="Close character sheet"
                    className="absolute top-4 right-4 z-10 font-display text-xl leading-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright"
                    style={{ color: "var(--gold-deep)" }}
                  >
                    ✕
                  </Dialog.Close>

                  <div className="overflow-y-auto max-h-[90vh] p-8">
                    {!char || !char.name ? (
                      <p className="font-body italic" style={{ color: "var(--ink-faded)" }}>No character data.</p>
                    ) : (
                      <>
                        {/* Double-page grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-0 md:divide-x md:divide-gold-deep/30">
                          {/* === LEFT PAGE: Identity + Stats === */}
                          <div className="pr-0 md:pr-8">
                            {/* Portrait circle */}
                            <div className="flex flex-col items-center mb-4">
                              <div
                                className="relative flex items-center justify-center"
                                style={{
                                  width: 120, height: 120,
                                  border: "2px solid var(--gold-deep)",
                                  borderRadius: "50%",
                                  background: "var(--parchment-aged)",
                                }}
                              >
                                <InitialSeal name={char.name} size={80} />
                              </div>
                              {/* Name */}
                              <h2
                                className="mt-3 font-display text-2xl uppercase text-center"
                                style={{ color: "var(--gold-bright)", letterSpacing: "0.18em" }}
                              >
                                {char.name}
                              </h2>
                              <p className="font-body italic text-sm" style={{ color: "var(--ink-secondary)" }}>
                                {char.archetype ?? ""} · Level {char.level}
                              </p>
                            </div>

                            <OrnamentDivider variant="flourish-c" className="!my-3" />

                            {/* Stats sigilli */}
                            <div className="grid grid-cols-3 gap-3 justify-items-center">
                              {ABILITY_ORDER.map((ab) => {
                                const score = (char.abilities as Record<string, number>)?.[ab] ?? 10;
                                return <StatSigil key={ab} name={ab} score={score} />;
                              })}
                            </div>

                            {hp && <HpBar current={hp.current} max={hp.max} />}

                            <div className="mt-3 flex gap-4 font-body text-sm" style={{ color: "var(--ink-secondary)" }}>
                              <span>AC <strong style={{ color: "var(--ink-primary)" }}>{char.ac}</strong></span>
                              <span>XP <strong style={{ color: "var(--ink-primary)" }}>{char.xp}</strong></span>
                              <span>Gold <strong style={{ color: "var(--gold-bright)" }}>{char.gold}</strong></span>
                            </div>
                          </div>

                          {/* === RIGHT PAGE: Inventory + Skills + Companions === */}
                          <div className="pl-0 md:pl-8 mt-6 md:mt-0">
                            {/* Inventory */}
                            <div className="mb-5">
                              <h4
                                className="mb-2 font-display text-[10px] uppercase"
                                style={{ color: "var(--ink-faded)", letterSpacing: "0.28em" }}
                              >
                                Inventory
                              </h4>
                              {(char.inventory ?? []).length === 0 ? (
                                <p className="font-body italic text-sm" style={{ color: "var(--ink-faded)" }}>Empty satchel.</p>
                              ) : (
                                <ul className="space-y-1">
                                  {(char.inventory ?? []).map((item, i) => (
                                    <li key={i} className="flex items-center gap-2 font-body text-sm" style={{ color: "var(--ink-primary)" }}>
                                      <span style={{ color: "var(--gold-deep)" }}>⚖</span>
                                      {item.name}
                                      {item.quantity > 1 && (
                                        <span style={{ color: "var(--ink-faded)" }}>×{item.quantity}</span>
                                      )}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>

                            {/* Skills */}
                            {char.skills && Object.keys(char.skills).length > 0 && (
                              <div className="mb-5">
                                <h4
                                  className="mb-2 font-display text-[10px] uppercase"
                                  style={{ color: "var(--ink-faded)", letterSpacing: "0.28em" }}
                                >
                                  Skills
                                </h4>
                                <ul className="space-y-1">
                                  {Object.entries(char.skills).map(([skill, data]) => (
                                    <li key={skill} className="flex justify-between font-body text-sm" style={{ color: "var(--ink-primary)" }}>
                                      <span className="flex items-center gap-2">
                                        <span style={{ color: "var(--gold-deep)" }}>◈</span>
                                        <span className="capitalize">{skill}</span>
                                      </span>
                                      <span style={{ color: "var(--ink-faded)" }}>Lv {data.level}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {/* Reputation */}
                            {char.reputation && Object.keys(char.reputation).length > 0 && (
                              <div className="mb-5">
                                <h4
                                  className="mb-2 font-display text-[10px] uppercase"
                                  style={{ color: "var(--ink-faded)", letterSpacing: "0.28em" }}
                                >
                                  Reputation
                                </h4>
                                <ul className="space-y-1">
                                  {Object.entries(char.reputation).map(([faction, score]) => (
                                    <li key={faction} className="flex justify-between font-body text-sm">
                                      <span style={{ color: "var(--ink-primary)" }}>{faction}</span>
                                      <span style={{ color: (score as number) >= 0 ? "var(--gold-bright)" : "var(--blood)" }}>
                                        {(score as number) >= 0 ? "+" : ""}{score as number}
                                      </span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* === BOTTOM STRIP: Background bio === */}
                        {char.background && (
                          <div
                            className="mt-6 pt-4"
                            style={{ borderTop: "1px solid var(--gold-deep)" }}
                          >
                            <h4
                              className="mb-2 text-center font-display text-[10px] uppercase"
                              style={{ color: "var(--ink-faded)", letterSpacing: "0.3em" }}
                            >
                              ◈ Background & Origin ◈
                            </h4>
                            <p className="font-body italic text-base leading-relaxed" style={{ color: "var(--ink-primary)" }}>
                              {char.background}
                            </p>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </motion.div>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
