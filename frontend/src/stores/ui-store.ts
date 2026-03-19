import { create } from "zustand";

interface UIState {
  sidePanel: "character" | "inventory" | "quests" | "map" | "settings" | null;
  showCompanionBar: boolean;
  soundEnabled: boolean;
  setSidePanel: (panel: UIState["sidePanel"]) => void;
  toggleSidePanel: (panel: NonNullable<UIState["sidePanel"]>) => void;
  setShowCompanionBar: (show: boolean) => void;
  setSoundEnabled: (enabled: boolean) => void;
}

export const useUIStore = create<UIState>()((set) => ({
  sidePanel: null,
  showCompanionBar: true,
  soundEnabled: true,
  setSidePanel: (panel) => set({ sidePanel: panel }),
  toggleSidePanel: (panel) =>
    set((state) => ({
      sidePanel: state.sidePanel === panel ? null : panel,
    })),
  setShowCompanionBar: (show) => set({ showCompanionBar: show }),
  setSoundEnabled: (enabled) => set({ soundEnabled: enabled }),
}));
