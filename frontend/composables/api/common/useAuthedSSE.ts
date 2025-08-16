import { onUnmounted, ref } from "vue";

import type { ComputedRef, Ref } from "vue";

export function useAuthedPOSTSSE(
  url: Ref<string> | ComputedRef<string> | string,
  body?:
    | Ref<Record<string, any>>
    | ComputedRef<Record<string, any>>
    | Record<string, any>
) {
  const data = ref("");
  const error = ref(false);
  let reader: ReadableStreamDefaultReader<string> | null = null;

  const urlRef = toRef(url);
  const bodyRef = toRef(body);

  const start = async () => {
    await stop();
    data.value = "";
    error.value = false;

    try {
      const response = await $fetch<ReadableStream>(urlRef.value, {
        method: "POST",
        body: bodyRef.value,
        responseType: "stream",
      });

      reader = response.pipeThrough(new TextDecoderStream()).getReader();

      while (reader) {
        const { value, done } = await reader.read();

        if (done) break;

        if (value) {
          data.value += value;
        }
      }
    } catch (_) {
      error.value = true;
    }
  };

  const stop = async () => {
    if (reader) {
      await reader.cancel();
      reader = null;
    }
  };

  onUnmounted(() => {
    stop();
  });

  return {
    data,
    error,
    start,
    stop,
  };
}
