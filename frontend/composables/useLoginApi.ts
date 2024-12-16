import { type Ref } from "vue";
import { useCustomFetch } from "./useCustomFetch";

interface LoginResponse {
  access_token: string;
  token_type: "bearer";
}

export async function useLoginApi(
  username: Ref<string> | ComputedRef<string>,
  password: Ref<string> | ComputedRef<string>
) {
  const authStore = useTokenStore();
  const body = computed(() => {
    const formData = new FormData();
    formData.append("grant_type", "password");
    formData.append("username", username.value);
    formData.append("password", password.value);
    return formData;
  });

  const {
    public: { apiBaseUrl },
  } = useRuntimeConfig();

  const {
    data,
    loading,
    error,
    send: login,
  } = await useCustomFetch<LoginResponse>("/auth/token", {
    method: "POST",
    baseURL: apiBaseUrl,
    body: body,
  });

  watch(data, (newData) => {
    if (!error.value && newData) {
      authStore.setToken(newData.access_token);
    }
  });

  return { loading, error, login };
}
