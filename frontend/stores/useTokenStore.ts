export const useTokenStore = defineStore("auth", () => {
  const token = useLocalStorage<string | null>("token", null);
  const hasToken = computed(() => token.value !== null);
  const setToken = (newToken: string) => {
    token.value = newToken;
  };
  const clearToken = () => {
    token.value = null;
  };
  return { token, hasToken, setToken, clearToken };
});
