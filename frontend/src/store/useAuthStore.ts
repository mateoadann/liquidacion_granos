import { create } from "zustand";
import { refreshToken as apiRefresh, getMe } from "../api/authApi";

interface User {
  id: number;
  username: string;
  nombre: string;
  rol: "admin" | "usuario";
}

interface AuthState {
  accessToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  isRestoring: boolean;
  setAuth: (token: string, user: User) => void;
  clearAuth: () => void;
  updateToken: (token: string) => void;
  restoreSession: () => Promise<void>;
}

let restorePromise: Promise<void> | null = null;

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  user: null,
  isAuthenticated: false,
  isRestoring: !!sessionStorage.getItem("refresh_token"),

  setAuth: (token, user) =>
    set({
      accessToken: token,
      user,
      isAuthenticated: true,
    }),

  clearAuth: () => {
    sessionStorage.removeItem("refresh_token");
    set({
      accessToken: null,
      user: null,
      isAuthenticated: false,
    });
  },

  updateToken: (token) =>
    set({
      accessToken: token,
    }),

  restoreSession: async () => {
    if (get().isAuthenticated) return;
    if (restorePromise) return restorePromise;

    const stored = sessionStorage.getItem("refresh_token");
    if (!stored) {
      set({ isRestoring: false });
      return;
    }

    set({ isRestoring: true });
    restorePromise = (async () => {
      try {
        const { access_token } = await apiRefresh(stored);
        const user = await getMe(access_token);
        set({ accessToken: access_token, user, isAuthenticated: true });
      } catch {
        sessionStorage.removeItem("refresh_token");
      } finally {
        set({ isRestoring: false });
        restorePromise = null;
      }
    })();
    return restorePromise;
  },
}));
