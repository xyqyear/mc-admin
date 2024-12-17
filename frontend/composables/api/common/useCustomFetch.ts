import type { ComputedRef, Ref } from "vue";

export interface UseCustomFetchOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  baseURL?: string;
  query?:
    | Ref<Record<string, string>>
    | ComputedRef<Record<string, string>>
    | Record<string, string>;
  headers?:
    | Ref<Record<string, string>>
    | ComputedRef<Record<string, string>>
    | Record<string, string>;
  body?:
    | Ref<FormData>
    | ComputedRef<FormData>
    | FormData
    | Ref<Record<string, any>>
    | ComputedRef<Record<string, any>>
    | Record<string, any>;
  timeout?: number;
  immediate?: boolean;
  watch?: boolean;
}

export async function useCustomFetch<T>(
  url: Ref<string> | ComputedRef<string> | string,
  {
    method,
    baseURL,
    query,
    headers,
    body,
    timeout,
    immediate = false,
    watch = false,
  }: UseCustomFetchOptions = {}
) {
  const data = ref<T | null>(null);
  const loading = ref(false);
  const error = ref(false);
  const statusCode = ref<number | null>(null);

  const useFetchWatch = watch ? undefined : watch;

  const { refresh } = await useFetch(url, {
    baseURL: baseURL,
    method: method,
    query: query,
    headers: headers,
    body: body,
    timeout: timeout,
    immediate: immediate,
    watch: useFetchWatch,
    onRequest: ({ options }) => {
      console.log("onRequest");
      console.log(options);

      loading.value = true;
      error.value = false;
      statusCode.value = null;
    },
    onRequestError: ({ error: requestError }) => {
      console.log("onRequestError");
      console.log(requestError);

      loading.value = false;
      error.value = true;
      statusCode.value = null;
    },
    onResponse: ({ response }) => {
      console.log("onResponse");
      console.log(response);

      loading.value = false;
      statusCode.value = response.status;

      if (response.ok) {
        error.value = false;
        data.value = response._data;
      } else {
        error.value = true;
      }
    },
  });
  return { data, loading, error, statusCode, send: refresh };
}
