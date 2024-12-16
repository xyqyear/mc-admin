import type { LoginPreference } from "~/types/LoginPreference";

export const useLoginPreferenceStore = defineStore("loginPreference", () => {
  const loginPreference = useLocalStorage<LoginPreference>(
    "loginPreference",
    "code"
  );
  const setLoginPreference = (newToken: LoginPreference) => {
    loginPreference.value = newToken;
  };
  return { loginPreference, setLoginPreference };
});
