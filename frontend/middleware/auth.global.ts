import { useTokenStore } from "~/stores/useTokenStore";

export default defineNuxtRouteMiddleware((to, _) => {
  // hasToken isn't reactive but we don't need it to be
  const { hasToken } = useTokenStore();

  if (to.path !== "/login" && !hasToken) {
    return navigateTo("/login");
  }
});
