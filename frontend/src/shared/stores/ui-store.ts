import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

export type ThemeOverride = "auto" | "dark" | "light";

interface UIState {
  sidePanel: "character" | "inventory" | "quests" | "map" | "settings" | null;
  showCompanionBar: boolean;
  soundEnabled: boolean;
  themeOverride: ThemeOverride;
  fontSize: number; // px, range 14-24
  setSidePanel: (panel: UIState["sidePanel"]) => void;
  toggleSidePanel: (panel: NonNullable<UIState["sidePanel"]>) => void;
  setShowCompanionBar: (show: boolean) => void;
  setSoundEnabled: (enabled: boolean) => void;
  setThemeOverride: (theme: ThemeOverride) => void;
  setFontSize: (size: number) => void;
}

export const useUIStore = create<UIState>()(
  devtools(
    persist(
    (set) => ({
      sidePanel: null,
      showCompanionBar: true,
      soundEnabled: true,
      themeOverride: "auto",
      fontSize: 18,
      setSidePanel: (panel) => set({ sidePanel: panel }),
      toggleSidePanel: (panel) =>
        set((state) => ({
          sidePanel: state.sidePanel === panel ? null : panel,
        })),
      setShowCompanionBar: (show) => set({ showCompanionBar: show }),
      setSoundEnabled: (enabled) => set({ soundEnabled: enabled }),
      setThemeOverride: (theme) => set({ themeOverride: theme }),
      setFontSize: (size) => set({ fontSize: Math.min(24, Math.max(14, size)) }),
    }),
    {
      name: "saga-ui",
      partialize: (state) => ({
        soundEnabled: state.soundEnabled,
        themeOverride: state.themeOverride,
        fontSize: state.fontSize,
      }),
    },
    ),
    { name: "ui-store", enabled: import.meta.env.DEV },
  ),
);
