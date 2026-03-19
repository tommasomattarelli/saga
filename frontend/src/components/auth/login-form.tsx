import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { login, getMe } from "../../services/api";
import { useAuthStore } from "../../stores/auth-store";

export default function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { setTokens, setUser } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const { data: tokens } = await login(username, password);
      setTokens(tokens);
      const { data: user } = await getMe();
      setUser(user);
      navigate("/campaigns");
    } catch {
      setError("Invalid credentials");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-md rounded-lg border border-parchment-700/30 bg-parchment-900/80 p-8 shadow-2xl">
        <h1 className="mb-2 text-center font-display text-3xl font-bold text-gold-400">
          SAGA
        </h1>
        <p className="mb-8 text-center text-sm text-parchment-400">
          AI Dungeon Master
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="rounded bg-blood-900/50 p-3 text-sm text-red-300">
              {error}
            </div>
          )}

          <div>
            <label className="mb-1 block text-sm text-parchment-300">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded border border-parchment-700/50 bg-parchment-900 px-3 py-2 text-parchment-100 focus:border-gold-500 focus:outline-none"
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-parchment-300">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-parchment-700/50 bg-parchment-900 px-3 py-2 text-parchment-100 focus:border-gold-500 focus:outline-none"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded bg-gold-500 px-4 py-2 font-semibold text-parchment-900 transition hover:bg-gold-400 disabled:opacity-50"
          >
            {loading ? "Entering..." : "Enter the Realm"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-parchment-400">
          New adventurer?{" "}
          <Link to="/register" className="text-gold-400 hover:underline">
            Create account
          </Link>
        </p>
      </div>
    </div>
  );
}
