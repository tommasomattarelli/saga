import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

const controlStyle = {
  color: "var(--ink-primary)",
  background: "var(--parchment-aged)",
  border: "1px solid var(--line-strong)",
};

export function SubHeader({ label }: { label: string }) {
  return (
    <h5
      className="mb-1.5 font-display text-xs font-semibold"
      style={{ color: "var(--ink-secondary)" }}
    >
      {label}
    </h5>
  );
}

export function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="mb-2">
      <label
        htmlFor={htmlFor}
        className="mb-1 block font-display text-xs"
        style={{ color: "var(--ink-faded)" }}
      >
        {label}
      </label>
      {children}
      {hint ? (
        <p className="mt-1 font-display text-[10px]" style={{ color: "var(--ink-faded)" }}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="w-full rounded-lg px-3 py-1.5 font-display text-sm focus:outline-none focus:ring-1 focus:ring-accent"
      style={controlStyle}
    />
  );
}

export function SelectInput(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className="w-full rounded-lg px-3 py-1.5 font-display text-sm focus:outline-none focus:ring-1 focus:ring-accent"
      style={controlStyle}
    />
  );
}

export function ActionButton({
  children,
  onClick,
  disabled,
  tone = "quiet",
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  tone?: "quiet" | "primary";
}) {
  const primary = tone === "primary";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-lg px-3 py-1.5 font-display text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent disabled:opacity-50"
      style={{
        color: primary ? "var(--parchment-aged)" : "var(--ink-secondary)",
        background: primary ? "var(--accent)" : "transparent",
        border: `1px solid ${primary ? "var(--accent)" : "var(--line-strong)"}`,
      }}
    >
      {children}
    </button>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="mt-1 font-display text-[11px]" style={{ color: "var(--blood)" }}>
      {children}
    </p>
  );
}
