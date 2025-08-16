import { ElNotification } from "element-plus";
import { storeToRefs } from "pinia";
import type { ComputedRef, Ref } from "vue";
import { useTokenStore } from "~/stores/useTokenStore";
import type { UseCustomFetchOptions } from "./useCustomFetch";
import { useCustomFetch } from "./useCustomFetch";

export async function useAuthedApi<T>(
  url: Ref<string> | ComputedRef<string> | string,
  {
    method,
    query,
    headers,
    body,
    timeout,
    immediate = false,
    watch: fetchWatch = false,
  }: UseCustomFetchOptions = {}
) {
  const { token } = storeToRefs(useTokenStore());
  const {
    public: { apiBaseUrl },
  } = useRuntimeConfig();

  const { data, loading, error, statusCode, send } = await useCustomFetch<T>(
    url,
    {
      method: method,
      baseURL: apiBaseUrl,
      query: query,
      headers: computed(() => {
        return {
          Authorization: `Bearer ${token.value}`,
          ...toValue(headers),
        };
      }),
      body: body,
      timeout: timeout,
      immediate: immediate,
      watch: fetchWatch,
    }
  );

  watch(statusCode, (newStatusCode) => {
    if (newStatusCode === 401) {
      navigateTo("/");
      ElNotification({
        title: "Error",
        message: "登录过期",
        type: "error",
      });
    } else if (newStatusCode === 403) {
      ElNotification({
        title: "Error",
        message: "权限不足",
        type: "error",
      });
    }
  });

  return { data, loading, error, statusCode, send };
}
