import { useEffect } from "react";
import { AntiqueMap } from "../../../assets/ornaments/antique-map";
import { SagaSeal } from "../../../assets/ornaments/saga-seal";
import { OrnateFrame } from "../../../shared/ui/ornate-frame";
import {
  FlourishB,
  FlourishC,
} from "../../../assets/ornaments/flourish-dividers";

interface AuthPageLayoutProps {
  /** Subtitle shown below SAGA seal on the left page */
  subtitle: string;
  /** Right page content — the actual form */
  children: React.ReactNode;
}

/* Tomo a doppia pagina con mappa antica di sfondo, tema DARK forzato */
export function AuthPageLayout({ subtitle, children }: AuthPageLayoutProps) {
  // Force dark theme on the root for this flow
  useEffect(() => {
    const prev = document.documentElement.getAttribute("data-theme");
    document.documentElement.setAttribute("data-theme", "dark");
    return () => {
      if (prev) document.documentElement.setAttribute("data-theme", prev);
      else document.documentElement.removeAttribute("data-theme");
    };
  }, []);

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden flex items-center justify-center p-8"
      style={{ background: "var(--parchment-base)" }}
    >
      {/* Full-bleed animated map */}
      <AntiqueMap animate />

      {/* Vignette to focus the tome */}
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 25%, rgba(0,0,0,0.75) 100%)",
        }}
      />

      {/* Tome card */}
      <div className="relative z-10 w-full max-w-[720px]">
        <OrnateFrame variant="large">
          <div
            className="grid grid-cols-2 gap-0 min-h-[420px]"
            style={{ background: "var(--parchment-aged)" }}
          >
            {/* Left page — SAGA identity */}
            <div className="flex flex-col items-center justify-center gap-5 px-6 py-4 relative">
              <SagaSeal size={140} color="var(--gold-bright)" animate />
              <h1
                className="font-display text-4xl uppercase text-center"
                style={{
                  color: "var(--gold-bright)",
                  letterSpacing: "0.22em",
                  fontWeight: 700,
                }}
              >
                SAGA
              </h1>
              <FlourishC width={200} color="var(--gold-deep)" />
              <p
                className="font-body italic text-center text-sm"
                style={{ color: "var(--ink-secondary)" }}
              >
                {subtitle}
              </p>
            </div>

            {/* Book spine divider */}
            <div
              aria-hidden="true"
              className="absolute left-1/2 top-0 bottom-0 w-px"
              style={{ background: "var(--gold-deep)", opacity: 0.4 }}
            />

            {/* Right page — form area */}
            <div className="flex flex-col justify-center px-6 py-4">
              {children}
            </div>
          </div>
          <div className="flex justify-center pt-3">
            <FlourishB width={360} color="var(--gold-deep)" />
          </div>
        </OrnateFrame>
      </div>
    </div>
  );
}
