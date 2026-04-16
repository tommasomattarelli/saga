import { useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useAuthStore } from "./shared/stores/auth-store";
import { useUIStore } from "./shared/stores/ui-store";
import { ErrorBoundary } from "./shared/ui/error-boundary";
import { NoiseOverlay } from "./shared/ui/noise-overlay";
import { VignetteLayer } from "./shared/ui/vignette-layer";
import { MoodLayer } from "./shared/ui/mood-layer";
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

/* Determine transition variant from the current path */
function useRouteVariant(pathname: string): "auth" | "game" | "campaigns" {
  if (pathname.startsWith("/game/")) return "game";
  if (pathname.startsWith("/campaigns")) return "campaigns";
  return "auth";
}

/* Check reduced-motion preference once */
const prefersReducedMotion =
  typeof window !== "undefined"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;

/* Variant sets keyed by the ENTERING route type */
const PAGE_VARIANTS = {
  auth: {
    initial: { opacity: 0, scale: 0.98 },
    animate: { opacity: 1, scale: 1 },
    exit:    { opacity: 0, scale: 0.98 },
  },
  campaigns: {
    initial: { opacity: 0, scale: 0.98 },
    animate: { opacity: 1, scale: 1 },
    exit:    { opacity: 0, scale: 0.98 },
  },
  game: {
    /* Page-turn: entering game = rotateY from 90° */
    initial: { opacity: 0, rotateY: 90 },
    animate: { opacity: 1, rotateY: 0 },
    exit:    { opacity: 0, rotateY: -90 },
  },
} as const;

const TRANSITION = {
  auth:      { duration: 0.4, ease: "easeOut" as const },
  campaigns: { duration: 0.4, ease: "easeOut" as const },
  game:      { duration: 0.6, ease: [0.77, 0, 0.175, 1] as number[] },
};

const REDUCED_VARIANTS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit:    { opacity: 0 },
};
const REDUCED_TRANSITION = { duration: 0.2 };

function AnimatedRoutes() {
  const location = useLocation();
  const variant = useRouteVariant(location.pathname);
  const variants = prefersReducedMotion ? REDUCED_VARIANTS : PAGE_VARIANTS[variant];
  const transition = prefersReducedMotion ? REDUCED_TRANSITION : TRANSITION[variant];

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        variants={variants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={transition}
        style={variant === "game" ? { perspective: 1600, transformStyle: "preserve-3d" } : undefined}
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

/* Apply fontSize + themeOverride from UIStore to DOM */
function useDisplaySettings() {
  const fontSize = useUIStore((s) => s.fontSize);
  const themeOverride = useUIStore((s) => s.themeOverride);

  useEffect(() => {
    document.documentElement.style.setProperty("--base-font-size", `${fontSize}px`);
  }, [fontSize]);

  useEffect(() => {
    if (themeOverride === "auto") {
      document.documentElement.removeAttribute("data-theme-override");
    } else {
      document.documentElement.setAttribute("data-theme-override", themeOverride);
    }
  }, [themeOverride]);
}

export default function App() {
  useDisplaySettings();
  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-parchment-900 relative">
        <NoiseOverlay />
        <VignetteLayer />
        <MoodLayer />
        {/* Skip-link per keyboard users */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[9999] focus:px-4 focus:py-2 focus:font-display focus:text-xs focus:uppercase"
          style={{ background: "var(--parchment-aged)", color: "var(--gold-bright)", border: "1px solid var(--gold-bright)" }}
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
