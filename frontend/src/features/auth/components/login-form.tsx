import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuthFlow } from "../hooks/use-auth-flow";
import { AuthPageLayout } from "./auth-page-layout";
import {
  AuthInput,
  AuthError,
  OrnateButton,
} from "./auth-form-parts";

export default function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { submit, isPending, error } = useAuthFlow("login");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit({ username, password });
  };

  return (
    <AuthPageLayout subtitle="An endless tale awaits.">
      <form onSubmit={handleSubmit} className="space-y-5">
        <AuthInput
          id="username"
          label="Name"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
        />
        <AuthInput
          id="password"
          label="Word of Passage"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />

        {error && <AuthError message={error} />}

        <div className="pt-2">
          <OrnateButton type="submit" disabled={isPending} className="w-full">
            {isPending ? "Opening…" : "Cross the Threshold"}
          </OrnateButton>
        </div>
      </form>

      <p
        className="mt-6 text-center text-xs font-body"
        style={{ color: "var(--ink-secondary)" }}
      >
        New to these lands?{" "}
        <Link
          to="/register"
          className="underline underline-offset-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
          style={{ color: "var(--gold-bright)" }}
        >
          Begin thy tale
        </Link>
      </p>
    </AuthPageLayout>
  );
}
