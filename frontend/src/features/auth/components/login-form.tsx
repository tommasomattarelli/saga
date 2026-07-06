import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthFlow } from "../hooks/use-auth-flow";
import { AuthPageLayout } from "./auth-page-layout";
import { AuthInput, AuthError, AuthButton } from "./auth-form-parts";

export default function LoginForm() {
  const { t } = useTranslation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { submit, isPending, error } = useAuthFlow("login");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit({ username, password });
  };

  return (
    <AuthPageLayout subtitle={t("auth.login_subtitle")}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <AuthInput
          id="username"
          label={t("auth.username")}
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
        />
        <AuthInput
          id="password"
          label={t("auth.password")}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />

        {error && <AuthError message={error} />}

        <div className="pt-2">
          <AuthButton type="submit" disabled={isPending} className="w-full">
            {isPending ? "…" : t("auth.login")}
          </AuthButton>
        </div>
      </form>

      <p className="mt-6 text-center text-xs font-display" style={{ color: "var(--ink-faded)" }}>
        {t("auth.no_account")}{" "}
        <Link
          to="/register"
          className="underline underline-offset-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
          style={{ color: "var(--accent)" }}
        >
          {t("auth.register")}
        </Link>
      </p>
    </AuthPageLayout>
  );
}
