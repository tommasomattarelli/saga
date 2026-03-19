import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./stores/auth-store";
import LoginForm from "./components/auth/login-form";
import RegisterForm from "./components/auth/register-form";
import GameView from "./components/game-view";
import CampaignSelect from "./components/campaign-select";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <div className="min-h-screen bg-parchment-900">
      <Routes>
        <Route path="/login" element={<LoginForm />} />
        <Route path="/register" element={<RegisterForm />} />
        <Route
          path="/campaigns"
          element={
            <ProtectedRoute>
              <CampaignSelect />
            </ProtectedRoute>
          }
        />
        <Route
          path="/game/:campaignId"
          element={
            <ProtectedRoute>
              <GameView />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/campaigns" replace />} />
      </Routes>
    </div>
  );
}
