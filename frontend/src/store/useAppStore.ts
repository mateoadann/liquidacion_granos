import { create } from "zustand";

type Environment = "homologacion" | "produccion";

interface AppState {
  environment: Environment;
  setEnvironment: (env: Environment) => void;
}

export const useAppStore = create<AppState>((set) => ({
  environment: "homologacion",
  setEnvironment: (env) => set({ environment: env }),
}));
