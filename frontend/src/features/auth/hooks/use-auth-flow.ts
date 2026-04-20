import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, register, getMe } from "../../../shared/api/client";
import { useAuthStore } from "../../../shared/stores/auth-store";
import type { AxiosError } from "axios";

interface AuthFlowResult {
  submit: (fields: AuthFields) => Promise<void>;
  isPending: boolean;
  error: string | null;
}

interface AuthFields {
  username: string;
  password: string;
  email?: string;
}

function classifyError(err: unknown): string {
  const status = (err as AxiosError)?.response?.status;
  if (!status) return "Network error. Check your connection.";
  if (status === 401 || status === 422) return "Invalid credentials.";
  if (status >= 400 && status < 500) return "Request failed. Check your details.";
  return "Server error. Please try again later.";
}

export function useAuthFlow(mode: "login" | "register"): AuthFlowResult {
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { setTokens, setUser } = useAuthStore();

  const submit = async (fields: AuthFields) => {
    setError(null);
    setIsPending(true);
    try {
      const { data: tokens } =
        mode === "login"
          ? await login(fields.username, fields.password)
          : await register(fields.username, fields.email!, fields.password);
      setTokens(tokens);
      const { data: user } = await getMe();
      setUser(user);
      navigate("/campaigns");
    } catch (err) {
      setError(classifyError(err));
    } finally {
      setIsPending(false);
    }
  };

  return { submit, isPending, error };
}
