import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuthFlow } from "../hooks/use-auth-flow";

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
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-md rounded-lg border border-parchment-700/30 bg-parchment-900/80 p-8 shadow-2xl">
        <h1 className="mb-2 text-center font-display text-3xl font-bold text-gold-400">SAGA</h1>
        <p className="mb-8 text-center text-sm text-parchment-400">Begin Your Journey</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div role="alert" aria-live="polite" className="rounded bg-blood-900/50 p-3 text-sm text-red-300">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="reg-username" className="mb-1 block text-sm text-parchment-300">
              Username
            </label>
            <input
              id="reg-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded border border-parchment-700/50 bg-parchment-900 px-3 py-2 text-parchment-100 focus:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500/40"
              required
              minLength={3}
            />
          </div>

          <div>
            <label htmlFor="reg-email" className="mb-1 block text-sm text-parchment-300">
              Email
            </label>
            <input
              id="reg-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded border border-parchment-700/50 bg-parchment-900 px-3 py-2 text-parchment-100 focus:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500/40"
              required
            />
          </div>

          <div>
            <label htmlFor="reg-password" className="mb-1 block text-sm text-parchment-300">
              Password
            </label>
            <input
              id="reg-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-parchment-700/50 bg-parchment-900 px-3 py-2 text-parchment-100 focus:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500/40"
              required
              minLength={8}
            />
          </div>

          <button
            type="submit"
            disabled={isPending}
            className="w-full rounded bg-gold-500 px-4 py-2 font-semibold text-parchment-900 transition hover:bg-gold-400 disabled:opacity-50"
          >
            {isPending ? "Forging your destiny..." : "Create Character"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-parchment-400">
          Already have an account?{" "}
          <Link to="/login" className="text-gold-400 hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
