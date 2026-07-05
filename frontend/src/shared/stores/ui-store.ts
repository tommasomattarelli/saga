import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

interface UIState {
  sidePanel: "character" | "inventory" | "quests" | "map" | "settings" | null;
  showCompanionBar: boolean;
  soundEnabled: boolean;
  fontSize: number; // px, range 14-24
  setSidePanel: (panel: UIState["sidePanel"]) => void;
  toggleSidePanel: (panel: NonNullable<UIState["sidePanel"]>) => void;
  setShowCompanionBar: (show: boolean) => void;
  setSoundEnabled: (enabled: boolean) => void;
  setFontSize: (size: number) => void;
}

export const useUIStore = create<UIState>()(
  devtools(
    persist(
      (set) => ({
        sidePanel: null,
        showCompanionBar: true,
        soundEnabled: true,
        fontSize: 18,
        setSidePanel: (panel) => set({ sidePanel: panel }),
        toggleSidePanel: (panel) =>
          set((state) => ({
            sidePanel: state.sidePanel === panel ? null : panel,
          })),
        setShowCompanionBar: (show) => set({ showCompanionBar: show }),
        setSoundEnabled: (enabled) => set({ soundEnabled: enabled }),
        setFontSize: (size) => set({ fontSize: Math.min(24, Math.max(14, size)) }),
      }),
      {
        name: "saga-ui",
        partialize: (state) => ({
          soundEnabled: state.soundEnabled,
          fontSize: state.fontSize,
        }),
      },
    ),
    { name: "ui-store", enabled: import.meta.env.DEV },
  ),
);
