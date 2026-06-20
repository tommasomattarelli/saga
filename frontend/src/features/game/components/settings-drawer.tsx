import { useNavigate } from "react-router-dom";
import { useUIStore, type ThemeOverride } from "../../../shared/stores/ui-store";
import { useAuthStore } from "../../../shared/stores/auth-store";
import { Drawer } from "../../../shared/ui/drawer";
import { OrnamentDivider } from "../../../shared/ui/ornament-divider";

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between cursor-pointer py-1.5">
      <span className="font-body text-sm" style={{ color: "var(--ink-primary)" }}>
        {label}
      </span>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className="relative focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
        style={{
          width: 40,
          height: 22,
          border: `1px solid ${checked ? "var(--gold-bright)" : "var(--gold-deep)"}`,
          background: checked ? "rgba(212, 175, 55, 0.25)" : "transparent",
          transition: "all 0.2s",
        }}
      >
        <span
          className="absolute top-[3px] transition-all"
          style={{
            width: 14,
            height: 14,
            background: checked ? "var(--gold-bright)" : "var(--ink-faded)",
            left: checked ? 22 : 4,
          }}
        />
      </button>
    </label>
  );
}

function SectionHeader({ label }: { label: string }) {
  return (
    <h4
      className="mt-4 mb-2 font-display text-[10px] uppercase"
      style={{ color: "var(--ink-faded)", letterSpacing: "0.28em" }}
    >
      {label}
    </h4>
  );
}

export default function SettingsDrawer() {
  const navigate = useNavigate();
  const sidePanel = useUIStore((s) => s.sidePanel);
  const setSidePanel = useUIStore((s) => s.setSidePanel);
  const soundEnabled = useUIStore((s) => s.soundEnabled);
  const setSoundEnabled = useUIStore((s) => s.setSoundEnabled);
  const themeOverride = useUIStore((s) => s.themeOverride);
  const setThemeOverride = useUIStore((s) => s.setThemeOverride);
  const fontSize = useUIStore((s) => s.fontSize);
  const setFontSize = useUIStore((s) => s.setFontSize);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const prefersReducedMotion =
    typeof window !== "undefined"
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false;

  return (
    <Drawer
      open={sidePanel === "settings"}
      onClose={() => setSidePanel(null)}
      title="Hand of Fate"
      width="w-[420px]"
    >
      {/* Audio */}
      <SectionHeader label="Audio" />
      <Toggle label="Dice sound" checked={soundEnabled} onChange={setSoundEnabled} />

      <OrnamentDivider variant="flourish-b" className="!my-3" />

      {/* Motion */}
      <SectionHeader label="Motion" />
      <div className="space-y-1">
        {(["auto", "reduced", "full"] as const).map((opt) => {
          const defaultOpt = prefersReducedMotion ? "reduced" : "auto";
          const isSelected = opt === defaultOpt; // read-only for now — store extension needed
          return (
            <button
              key={opt}
              disabled
              className="w-full text-left px-3 py-1.5 font-body text-sm focus-visible:outline-none"
              style={{
                border: `1px solid ${isSelected ? "var(--gold-bright)" : "var(--gold-deep)"}`,
                background: isSelected ? "rgba(212, 175, 55, 0.08)" : "transparent",
                color: "var(--ink-secondary)",
                opacity: opt !== defaultOpt ? 0.5 : 1,
              }}
            >
              {opt === "auto" ? "Auto (follow OS)" : opt === "reduced" ? "Reduced" : "Full"}
            </button>
          );
        })}
        <p className="font-body text-xs italic" style={{ color: "var(--ink-faded)" }}>
          Motion preferences — full control coming in a future update.
        </p>
      </div>

      <OrnamentDivider variant="flourish-c" className="!my-3" />

      {/* Display */}
      <SectionHeader label="Display" />

      {/* Theme override */}
      <div className="mb-3">
        <span className="font-body text-xs mb-1.5 block" style={{ color: "var(--ink-faded)" }}>
          Theme
        </span>
        <div className="flex gap-2">
          {(["auto", "light", "dark"] as ThemeOverride[]).map((opt) => (
            <button
              key={opt}
              onClick={() => setThemeOverride(opt)}
              className="flex-1 py-1.5 font-display text-[10px] uppercase tracking-grimoire focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright capitalize"
              style={{
                border: `1px solid ${themeOverride === opt ? "var(--gold-bright)" : "var(--gold-deep)"}`,
                background: themeOverride === opt ? "rgba(212,175,55,0.12)" : "transparent",
                color: themeOverride === opt ? "var(--gold-bright)" : "var(--ink-secondary)",
              }}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>

      {/* Font size slider */}
      <div className="mb-1">
        <div className="flex justify-between mb-1">
          <span className="font-body text-xs" style={{ color: "var(--ink-faded)" }}>
            Text size
          </span>
          <span className="font-display text-xs" style={{ color: "var(--gold-bright)" }}>
            {fontSize}px
          </span>
        </div>
        <input
          type="range"
          min={14}
          max={24}
          value={fontSize}
          onChange={(e) => setFontSize(Number(e.target.value))}
          className="w-full accent-gold-bright"
          style={{ accentColor: "var(--gold-bright)" }}
        />
        <div
          className="flex justify-between font-body text-[10px]"
          style={{ color: "var(--ink-faded)" }}
        >
          <span>A</span>
          <span>A</span>
        </div>
      </div>

      <OrnamentDivider variant="flourish-d" className="!my-3" />

      {/* Account */}
      <SectionHeader label="Account" />
      {user && (
        <div className="mb-3 font-body text-sm" style={{ color: "var(--ink-secondary)" }}>
          <span style={{ color: "var(--ink-faded)" }}>Signed in as: </span>
          <span style={{ color: "var(--ink-primary)" }}>{user.email ?? user.username}</span>
        </div>
      )}
      <button
        onClick={() => {
          logout();
          setSidePanel(null);
          navigate("/login");
        }}
        className="w-full py-2 font-display text-xs uppercase tracking-grimoire-wide focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
        style={{
          color: "var(--ink-faded)",
          border: "1px solid var(--gold-deep)",
        }}
      >
        Depart
      </button>
    </Drawer>
  );
}
