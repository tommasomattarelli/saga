import { forwardRef } from "react";

/* Boxed input with a visible field — label above, accent ring on focus */
interface AuthInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export const AuthInput = forwardRef<HTMLInputElement, AuthInputProps>(function AuthInput(
  { label, id, className = "", ...rest },
  ref,
) {
  return (
    <div>
      <label
        htmlFor={id}
        className="font-display text-xs block mb-1.5"
        style={{ color: "var(--ink-secondary)" }}
      >
        {label}
      </label>
      <input
        ref={ref}
        id={id}
        {...rest}
        className={`w-full rounded-lg px-3 py-2 font-display text-sm focus:outline-none focus:ring-1 focus:ring-accent ${className}`}
        style={{
          color: "var(--ink-primary)",
          background: "var(--parchment-aged)",
          border: "1px solid var(--line-strong)",
        }}
      />
    </div>
  );
});

/* Primary CTA — quiet outline, accent text */
export function AuthButton({
  children,
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={`rounded-lg px-6 py-2.5 font-display text-sm font-semibold disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent ${className}`}
      style={{
        color: "var(--accent)",
        border: "1px solid var(--accent)",
        background: "transparent",
      }}
    >
      {children}
    </button>
  );
}

/* Inline error */
export function AuthError({ message }: { message: string }) {
  return (
    <div
      role="alert"
      aria-live="polite"
      className="rounded-lg px-3 py-2 font-display text-sm"
      style={{ color: "var(--blood)", border: "1px solid var(--blood-dark)" }}
    >
      {message}
    </div>
  );
}
