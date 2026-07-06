import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthFlow } from "../hooks/use-auth-flow";
import { AuthPageLayout } from "./auth-page-layout";
import { AuthInput, AuthError, AuthButton } from "./auth-form-parts";

export default function RegisterForm() {
  const { t } = useTranslation();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { submit, isPending, error } = useAuthFlow("register");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit({ username, email, password });
  };

  return (
    <AuthPageLayout subtitle={t("auth.register_subtitle")}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <AuthInput
          id="reg-username"
          label={t("auth.username")}
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
          minLength={3}
        />
        <AuthInput
          id="reg-email"
          label={t("auth.email")}
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />
        <AuthInput
          id="reg-password"
          label={t("auth.password")}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          required
          minLength={8}
        />

        {error && <AuthError message={error} />}

        <div className="pt-2">
          <AuthButton type="submit" disabled={isPending} className="w-full">
            {isPending ? "…" : t("auth.register")}
          </AuthButton>
        </div>
      </form>

      <p className="mt-6 text-center text-xs font-display" style={{ color: "var(--ink-faded)" }}>
        {t("auth.have_account")}{" "}
        <Link
          to="/login"
          className="underline underline-offset-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
          style={{ color: "var(--accent)" }}
        >
          {t("auth.login")}
        </Link>
      </p>
    </AuthPageLayout>
  );
}
