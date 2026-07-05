import { useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useAuthStore } from "./shared/stores/auth-store";
import { useUIStore } from "./shared/stores/ui-store";
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

/* Check reduced-motion preference once */
const prefersReducedMotion =
  typeof window !== "undefined"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;

/* Flat fade between routes (calm; no page-turn) */
const PAGE_VARIANTS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
};
const TRANSITION = { duration: prefersReducedMotion ? 0.2 : 0.3, ease: "easeOut" as const };

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        variants={PAGE_VARIANTS}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={TRANSITION}
      >
        <Routes location={location}>
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
      </motion.div>
    </AnimatePresence>
  );
}

/* Apply fontSize from UIStore to DOM */
function useDisplaySettings() {
  const fontSize = useUIStore((s) => s.fontSize);

  useEffect(() => {
    document.documentElement.style.setProperty("--base-font-size", `${fontSize}px`);
  }, [fontSize]);
}

export default function App() {
  useDisplaySettings();
  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-parchment-900 relative">
        {/* Skip-link per keyboard users */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[9999] focus:px-4 focus:py-2 focus:font-display focus:text-xs focus:uppercase"
          style={{
            background: "var(--parchment-aged)",
            color: "var(--gold-bright)",
            border: "1px solid var(--gold-bright)",
          }}
        >
          Skip to content
        </a>
        <div className="relative z-10" id="main-content">
          <AnimatedRoutes />
        </div>
      </div>
    </ErrorBoundary>
  );
}
