import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useUIStore } from "../../../shared/stores/ui-store";
import { useAuthStore } from "../../../shared/stores/auth-store";
import { Drawer } from "../../../shared/ui/drawer";

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
      <span className="font-display text-sm" style={{ color: "var(--ink-primary)" }}>
        {label}
      </span>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className="relative rounded-full focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
        style={{
          width: 40,
          height: 22,
          border: `1px solid ${checked ? "var(--accent)" : "var(--line-strong)"}`,
          background: "transparent",
          transition: "all 0.2s",
        }}
      >
        <span
          className="absolute top-[3px] rounded-full transition-all"
          style={{
            width: 14,
            height: 14,
            background: checked ? "var(--accent)" : "var(--ink-faded)",
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
      className="mt-5 mb-2 font-display text-xs font-semibold"
      style={{ color: "var(--ink-faded)" }}
    >
      {label}
    </h4>
  );
}

function SectionRule() {
  return <div className="mt-4 h-px" style={{ background: "var(--line)" }} aria-hidden="true" />;
}

export default function SettingsDrawer() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const sidePanel = useUIStore((s) => s.sidePanel);
  const setSidePanel = useUIStore((s) => s.setSidePanel);
  const soundEnabled = useUIStore((s) => s.soundEnabled);
  const setSoundEnabled = useUIStore((s) => s.setSoundEnabled);
  const fontSize = useUIStore((s) => s.fontSize);
  const setFontSize = useUIStore((s) => s.setFontSize);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const prefersReducedMotion =
    typeof window !== "undefined"
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false;

  const motionOptions = [
    { key: "auto", label: t("settings.motion_auto") },
    { key: "reduced", label: t("settings.motion_reduced") },
    { key: "full", label: t("settings.motion_full") },
  ] as const;
  const defaultMotion = prefersReducedMotion ? "reduced" : "auto";

  return (
    <Drawer
      open={sidePanel === "settings"}
      onClose={() => setSidePanel(null)}
      title={t("game.settings")}
      width="w-[420px]"
    >
      {/* Audio */}
      <SectionHeader label={t("settings.audio")} />
      <Toggle label={t("settings.dice_sound")} checked={soundEnabled} onChange={setSoundEnabled} />

      <SectionRule />

      {/* Motion */}
      <SectionHeader label={t("settings.motion")} />
      <div className="space-y-1">
        {motionOptions.map((opt) => {
          const isSelected = opt.key === defaultMotion; // read-only for now — store extension needed
          return (
            <button
              key={opt.key}
              disabled
              className="w-full rounded-lg px-3 py-1.5 text-left font-display text-sm focus-visible:outline-none"
              style={{
                border: `1px solid ${isSelected ? "var(--line-strong)" : "var(--line)"}`,
                color: "var(--ink-secondary)",
                opacity: isSelected ? 1 : 0.5,
              }}
            >
              {opt.label}
            </button>
          );
        })}
        <p className="font-display text-xs" style={{ color: "var(--ink-faded)" }}>
          {t("settings.motion_note")}
        </p>
      </div>

      <SectionRule />

      {/* Display */}
      <SectionHeader label={t("settings.display")} />
      <div className="mb-1">
        <div className="mb-1 flex justify-between">
          <span className="font-display text-xs" style={{ color: "var(--ink-faded)" }}>
            {t("settings.text_size")}
          </span>
          <span className="font-display text-xs font-semibold" style={{ color: "var(--accent)" }}>
            {fontSize}px
          </span>
        </div>
        <input
          type="range"
          min={14}
          max={24}
          value={fontSize}
          onChange={(e) => setFontSize(Number(e.target.value))}
          className="w-full"
          style={{ accentColor: "var(--accent)" }}
        />
        <div
          className="flex justify-between font-display text-[10px]"
          style={{ color: "var(--ink-faded)" }}
        >
          <span>A</span>
          <span>A</span>
        </div>
      </div>

      <SectionRule />

      {/* Account */}
      <SectionHeader label={t("settings.account")} />
      {user && (
        <div className="mb-3 font-display text-sm" style={{ color: "var(--ink-secondary)" }}>
          <span style={{ color: "var(--ink-faded)" }}>{t("settings.signed_in_as")}: </span>
          <span style={{ color: "var(--ink-primary)" }}>{user.email ?? user.username}</span>
        </div>
      )}
      <button
        onClick={() => {
          logout();
          setSidePanel(null);
          navigate("/login");
        }}
        className="w-full rounded-lg py-2 font-display text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
        style={{ color: "var(--ink-secondary)", border: "1px solid var(--line-strong)" }}
      >
        {t("auth.logout")}
      </button>
    </Drawer>
  );
}
