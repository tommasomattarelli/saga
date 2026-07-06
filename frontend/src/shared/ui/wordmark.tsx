/* SAGA wordmark — sans caps, wide tracking (ADR 0013 F1) */
export function Wordmark({ size = "text-base" }: { size?: string }) {
  return (
    <span
      className={`font-display ${size} font-semibold select-none`}
      style={{ color: "var(--ink-primary)", letterSpacing: "0.28em" }}
    >
      SAGA
    </span>
  );
}
