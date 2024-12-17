import { useTokenStore } from "~/stores/useTokenStore";

interface CodeMessage {
  type: "code";
  code: string;
  timeout: number;
}

interface VerifiedMessage {
  type: "verified";
  access_token: string;
}

type ServerMessage = CodeMessage | VerifiedMessage;

export function useCodeLoginApi() {
  const code = ref("加载中");
  const timeout = ref(60);
  const countdown = ref(0);
  const success = ref(false);

  const {
    public: { apiBaseUrl },
  } = useRuntimeConfig();

  const { setToken } = useTokenStore();

  const originalUrl = apiBaseUrl as string;
  // declare apiBaseUrl as a string
  const wsBaseUrl: string = originalUrl
    .replace("https", "wss")
    .replace("http", "ws")
    .replace(/\/$/, "");

  const { data, open, close } = useWebSocket<string>(`${wsBaseUrl}/auth/code`, {
    heartbeat: true,
    immediate: false,
  });

  watch(data, (newData) => {
    if (newData) {
      if (newData === "pong") {
        return;
      }
      const data = JSON.parse(newData) as ServerMessage;
      if (data.type === "code") {
        code.value = data.code;
        timeout.value = data.timeout;
        countdown.value = data.timeout;
      } else if (data.type === "verified") {
        success.value = true;
        setToken(data.access_token);
      }
    }
  });

  // countdown timeout every second until reaches 0
  setInterval(() => {
    if (countdown.value > 0) {
      countdown.value -= 1;
    }
  }, 1000);

  return { code, timeout, countdown, success, open, close };
}
