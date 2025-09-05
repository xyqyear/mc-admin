import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type LoginPreference = "password" | "code";

interface LoginPreferenceStore {
  loginPreference: LoginPreference;
  setLoginPreference: (preference: LoginPreference) => void;
  toggleLoginPreference: () => void;
}

export const useLoginPreferenceStore = create<LoginPreferenceStore>()(
  persist(
    (set, get) => ({
      loginPreference: "code",
      setLoginPreference: (preference: LoginPreference) =>
        set({ loginPreference: preference }),
      toggleLoginPreference: () => {
        const { loginPreference } = get();
        set({
          loginPreference: loginPreference === "password" ? "code" : "password",
        });
      },
    }),
    {
      name: "mc-admin-login-preference",
      storage: createJSONStorage(() => localStorage),
      version: 1,
    }
  )
);

// Selector hooks for better performance
export const useLoginPreference = () =>
  useLoginPreferenceStore((state) => state.loginPreference);
