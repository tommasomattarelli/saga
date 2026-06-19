import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuthFlow } from "../hooks/use-auth-flow";
import { AuthPageLayout } from "./auth-page-layout";
import { AuthInput, AuthError, OrnateButton } from "./auth-form-parts";

export default function RegisterForm() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { submit, isPending, error } = useAuthFlow("register");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit({ username, email, password });
  };

  return (
    <AuthPageLayout subtitle="Inscribe thy name into the tome.">
      <form onSubmit={handleSubmit} className="space-y-4">
        <AuthInput
          id="reg-username"
          label="Name"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
          minLength={3}
        />
        <AuthInput
          id="reg-email"
          label="Sigil (email)"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />
        <AuthInput
          id="reg-password"
          label="Word of Passage"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          required
          minLength={8}
        />

        {error && <AuthError message={error} />}

        <div className="pt-2">
          <OrnateButton type="submit" disabled={isPending} className="w-full">
            {isPending ? "Forging…" : "Begin Thy Tale"}
          </OrnateButton>
        </div>
      </form>

      <p className="mt-6 text-center text-xs font-body" style={{ color: "var(--ink-secondary)" }}>
        Already of these lands?{" "}
        <Link
          to="/login"
          className="underline underline-offset-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
          style={{ color: "var(--gold-bright)" }}
        >
          Cross the threshold
        </Link>
      </p>
    </AuthPageLayout>
  );
}
