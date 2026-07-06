import { Wordmark } from "../../../shared/ui/wordmark";

interface AuthPageLayoutProps {
  /** Line under the wordmark */
  subtitle: string;
  /** The form */
  children: React.ReactNode;
}

/* Centered auth card — elevated surface against the page ground */
export function AuthPageLayout({ subtitle, children }: AuthPageLayoutProps) {
  return (
    <div
      className="min-h-screen w-full flex items-center justify-center p-8"
      style={{ background: "var(--parchment-shadow)" }}
    >
      <div
        className="w-full max-w-[360px] rounded-xl px-8 py-9"
        style={{
          background: "var(--parchment-base)",
          border: "1px solid var(--line-strong)",
        }}
      >
        <h1 className="mb-1">
          <Wordmark size="text-lg" />
        </h1>
        <p className="mb-7 font-display text-sm" style={{ color: "var(--ink-faded)" }}>
          {subtitle}
        </p>
        {children}
      </div>
    </div>
  );
}
