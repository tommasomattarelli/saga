import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./shared/stores/auth-store";
import { ErrorBoundary } from "./shared/ui/error-boundary";
import LoginForm from "./features/auth/components/login-form";
import RegisterForm from "./features/auth/components/register-form";
import GameView from "./features/game/components/game-view";
import CampaignSelect from "./features/campaign/components/campaign-select";
import NewCampaign from "./features/campaign/components/new-campaign";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-parchment-900">
        <Routes>
          <Route path="/login" element={<LoginForm />} />
          <Route path="/register" element={<RegisterForm />} />
          <Route
            path="/campaigns/new"
            element={
              <ProtectedRoute>
                <NewCampaign />
              </ProtectedRoute>
            }
          />
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
    </ErrorBoundary>
  );
}
