import { getApiBaseUrl } from "@/utils/api";
import { useCallback, useEffect, useRef, useState } from "react";

export interface WebSocketMessage {
  type: "log" | "error" | "info";
  content?: string;
  message?: string;
}

export type ConnectionState =
  | "DISCONNECTED"
  | "CONNECTING"
  | "CONNECTED"
  | "ERROR"
  | "RETRYING";

const MAX_RETRY_COUNT = 5;
// Exponential back-off; each index corresponds to the n-th retry.
const RETRY_DELAYS = [1000, 2000, 4000, 8000, 16000];

export interface UseServerConsoleWebSocketReturn {
  connectionState: ConnectionState;
  lastError: string | null;
  connect: (cols: number, rows: number) => void;
  disconnect: () => void;
  sendInput: (data: string) => void;
  sendResize: (cols: number, rows: number) => void;
  onMessage: (callback: (message: WebSocketMessage) => void) => void;
  removeMessageListener: (
    callback: (message: WebSocketMessage) => void,
  ) => void;
}

export const useServerConsoleWebSocket = (
  serverId: string,
  canConnect: boolean = true,
): UseServerConsoleWebSocketReturn => {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);
  const lastSizeRef = useRef<{ cols: number; rows: number } | null>(null);
  const messageCallbacksRef = useRef<Set<(message: WebSocketMessage) => void>>(
    new Set(),
  );

  const [connectionState, setConnectionState] =
    useState<ConnectionState>("DISCONNECTED");
  const [lastError, setLastError] = useState<string | null>(null);

  // connect/scheduleReconnect reference each other; refs break the cycle so
  // useCallback dependencies stay stable.
  const connectWebSocketRef = useRef<(cols: number, rows: number) => void>(undefined);
  const scheduleReconnectRef = useRef<() => void>(undefined);

  const buildWebSocketUrl = useCallback(
    (cols: number, rows: number) => {
      if (!serverId) return null;
      const baseUrl = getApiBaseUrl(true);
      return `${baseUrl}/servers/${serverId}/console?cols=${cols}&rows=${rows}`;
    },
    [serverId],
  );

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      const ws = wsRef.current;
      wsRef.current = null;

      // Drop handlers before close() so onclose can't trigger a reconnect race.
      ws.onopen = null;
      ws.onmessage = null;
      ws.onclose = null;
      ws.onerror = null;

      if (
        ws.readyState === WebSocket.CONNECTING ||
        ws.readyState === WebSocket.OPEN
      ) {
        ws.close(1000);
      }
    }

    setConnectionState("DISCONNECTED");
  }, []);

  const handleWebSocketMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);

        messageCallbacksRef.current.forEach((callback) => {
          callback(message);
        });

        switch (message.type) {
          case "error":
            if (message.message) {
              setLastError(message.message);
              disconnect();
              if (scheduleReconnectRef.current) {
                scheduleReconnectRef.current();
              }
            }
            break;
        }
      } catch (error) {
        console.error("Failed to parse WebSocket message:", error);
      }
    },
    [disconnect],
  );

  const connect = useCallback(
    (cols: number, rows: number) => {
      if (
        wsRef.current &&
        (wsRef.current.readyState === WebSocket.CONNECTING ||
          wsRef.current.readyState === WebSocket.OPEN)
      ) {
        disconnect();
      }

      if (!serverId) {
        return;
      }

      lastSizeRef.current = { cols, rows };

      const wsUrl = buildWebSocketUrl(cols, rows);
      if (!wsUrl) {
        console.error("Failed to build WebSocket URL");
        return;
      }

      setConnectionState("CONNECTING");
      setLastError(null);

      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          // Stale handler firing for a superseded socket — drop it.
          if (wsRef.current !== ws) {
            ws.close();
            return;
          }

          console.log("WebSocket connected");
          setConnectionState("CONNECTED");
          retryCountRef.current = 0;
        };

        ws.onmessage = handleWebSocketMessage;

        ws.onclose = (event) => {
          if (wsRef.current !== ws) {
            return;
          }

          console.log("WebSocket disconnected:", event.code, event.reason);
          wsRef.current = null;
          setConnectionState("DISCONNECTED");

          // 1000/1001 indicate a clean close; anything else is treated as a recoverable failure.
          if (event.code !== 1000 && event.code !== 1001) {
            if (scheduleReconnectRef.current) {
              scheduleReconnectRef.current();
            }
          }
        };

        ws.onerror = (error) => {
          if (wsRef.current !== ws) {
            return;
          }

          console.error("WebSocket error:", error);
          setConnectionState("ERROR");
          setLastError("WebSocket connection error");
        };
      } catch (error) {
        console.error("Failed to create WebSocket:", error);
        setConnectionState("ERROR");
        setLastError("Failed to create WebSocket connection");
      }
    },
    [serverId, buildWebSocketUrl, handleWebSocketMessage, disconnect],
  );

  const scheduleReconnect = useCallback(() => {
    if (retryCountRef.current >= MAX_RETRY_COUNT) {
      setConnectionState("ERROR");
      setLastError(`Maximum retry attempts (${MAX_RETRY_COUNT}) exceeded`);
      return;
    }

    if (!lastSizeRef.current) {
      setConnectionState("ERROR");
      setLastError("Cannot reconnect: no terminal size available");
      return;
    }

    const delay =
      RETRY_DELAYS[Math.min(retryCountRef.current, RETRY_DELAYS.length - 1)];
    retryCountRef.current++;

    setConnectionState("RETRYING");

    const { cols, rows } = lastSizeRef.current;
    reconnectTimeoutRef.current = setTimeout(() => {
      if (connectWebSocketRef.current) {
        connectWebSocketRef.current(cols, rows);
      }
    }, delay);
  }, []);

  connectWebSocketRef.current = connect;
  scheduleReconnectRef.current = scheduleReconnect;

  const sendInput = useCallback((data: string) => {
    if (
      !wsRef.current ||
      wsRef.current.readyState !== WebSocket.OPEN ||
      !data
    ) {
      return;
    }

    try {
      wsRef.current.send(
        JSON.stringify({
          type: "input",
          data: data,
        }),
      );
    } catch (error) {
      console.error("Failed to send input:", error);
    }
  }, []);

  const sendResize = useCallback((cols: number, rows: number) => {
    if (
      !wsRef.current ||
      wsRef.current.readyState !== WebSocket.OPEN ||
      cols <= 0 ||
      rows <= 0
    ) {
      return;
    }

    try {
      wsRef.current.send(
        JSON.stringify({
          type: "resize",
          width: cols,
          height: rows,
        }),
      );
    } catch (error) {
      console.error("Failed to send resize:", error);
    }
  }, []);

  const onMessage = useCallback(
    (callback: (message: WebSocketMessage) => void) => {
      messageCallbacksRef.current.add(callback);
    },
    [],
  );

  const removeMessageListener = useCallback(
    (callback: (message: WebSocketMessage) => void) => {
      messageCallbacksRef.current.delete(callback);
    },
    [],
  );

  // Auto-connect using the last known terminal size whenever canConnect flips on.
  useEffect(() => {
    if (canConnect && lastSizeRef.current) {
      const { cols, rows } = lastSizeRef.current;
      const timeoutId = setTimeout(() => {
        connect(cols, rows);
      }, 100);

      return () => {
        clearTimeout(timeoutId);
        disconnect();
      };
    } else if (!canConnect) {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [canConnect, connect, disconnect]);

  useEffect(() => {
    retryCountRef.current = 0;
    setLastError(null);
  }, [serverId]);

  return {
    connectionState,
    lastError,
    connect,
    disconnect,
    sendInput,
    sendResize,
    onMessage,
    removeMessageListener,
  };
};
