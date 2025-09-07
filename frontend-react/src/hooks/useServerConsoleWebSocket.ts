import { log } from "@/utils/devLogger";
import { getApiBaseUrl } from "@/utils/api";
import { useCallback, useEffect, useRef, useState } from "react";

// WebSocket消息类型
interface WebSocketMessage {
  type:
    | "log"
    | "command_result"
    | "error"
    | "info"
    | "filter_updated"
    | "logs_refreshed";
  content?: string;
  command?: string;
  result?: string;
  message?: string;
  filter_rcon?: boolean;
}

interface UseServerConsoleWebSocketProps {
  serverId: string;
  token: string;
  filterRcon: boolean;
  onLogsUpdate: (content: string) => void;
  onLogsRefresh: (content: string) => void;
  onCommandResult: (command: string, result: string) => void;
  onError: (message: string) => void;
  onInfo: (message: string) => void;
  onAutoScrollEnable?: () => void;
}

interface UseServerConsoleWebSocketReturn {
  isConnected: boolean;
  isConnecting: boolean;
  connect: () => void;
  disconnect: () => void;
  sendCommand: (command: string) => boolean;
  sendFilterUpdate: (filterRcon: boolean) => void;
  requestLogRefresh: () => void;
}

export function useServerConsoleWebSocket({
  serverId,
  token,
  filterRcon,
  onLogsUpdate,
  onLogsRefresh,
  onCommandResult,
  onError,
  onInfo,
  onAutoScrollEnable,
}: UseServerConsoleWebSocketProps): UseServerConsoleWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const prevFilterRconRef = useRef<boolean>(filterRcon);

  // 构建WebSocket URL
  const buildWebSocketUrl = useCallback(() => {
    if (!serverId || !token) return null;

    const baseUrl = getApiBaseUrl(true);
    return `${baseUrl}/servers/${serverId}/console?token=${encodeURIComponent(token)}`;
  }, [serverId, token]);

  // 发送过滤设置到后端
  const sendFilterUpdate = useCallback((newFilterRcon: boolean) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: "set_filter",
          filter_rcon: newFilterRcon,
        })
      );
      log.log("Filter setting sent to backend:", newFilterRcon);
    }
  }, []);

  // 请求刷新日志
  const requestLogRefresh = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: "refresh_logs",
        })
      );
      log.log("Log refresh requested");
    }
  }, []);

  // 发送命令
  const sendCommand = useCallback((command: string) => {
    if (
      !command.trim() ||
      !wsRef.current ||
      wsRef.current.readyState !== WebSocket.OPEN
    ) {
      return false;
    }

    try {
      wsRef.current.send(
        JSON.stringify({
          type: "command",
          command: command.trim(),
        })
      );
      log.log("Command sent:", command.trim());
      return true;
    } catch (error) {
      log.error("Failed to send command:", error);
      return false;
    }
  }, []);

  // WebSocket消息处理
  const handleMessage = useCallback(
    (event: MessageEvent) => {
      log.log("WebSocket message received:", event.data);

      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        log.log("Parsed message:", message);

        switch (message.type) {
          case "log":
            if (message.content) {
              log.log("Adding log content to display");
              onLogsUpdate(message.content);
            }
            break;

          case "logs_refreshed":
            // 刷新日志时替换整个日志内容
            if (message.content !== undefined) {
              log.log("Refreshing logs with filtered content");
              onLogsRefresh(message.content);
              onAutoScrollEnable?.();
            }
            break;

          case "filter_updated":
            // 过滤器更新确认
            if (message.filter_rcon !== undefined) {
              log.log(
                "Filter updated confirmation received:",
                message.filter_rcon
              );
            }
            break;

          case "command_result":
            if (message.command && message.result) {
              onCommandResult(message.command, message.result);
              onAutoScrollEnable?.();
            }
            break;

          case "error":
            if (message.message) {
              onError(message.message);
            }
            break;

          case "info":
            if (message.message) {
              onInfo(message.message);
            }
            break;
        }
      } catch (e) {
        log.error("Failed to parse WebSocket message:", e);
      }
    },
    [
      onLogsUpdate,
      onLogsRefresh,
      onCommandResult,
      onError,
      onInfo,
      onAutoScrollEnable,
    ]
  );

  // 连接WebSocket
  const connect = useCallback(() => {
    if (!serverId || !token) {
      log.log("Cannot connect WebSocket: missing serverId or token", {
        serverId,
        token: !!token,
      });
      return;
    }

    const wsUrl = buildWebSocketUrl();
    if (!wsUrl) {
      log.error("Failed to build WebSocket URL");
      return;
    }

    log.log("Starting WebSocket connection...");
    setIsConnecting(true);

    try {
      wsRef.current = new WebSocket(wsUrl);
      log.log("WebSocket object created, URL:", wsUrl);

      wsRef.current.onopen = () => {
        log.log("WebSocket onopen event fired");
        setIsConnected(true);
        setIsConnecting(false);
        log.log("WebSocket connected to server console, state updated");

        // Send initial filter setting to backend
        setTimeout(() => {
          sendFilterUpdate(filterRcon);
        }, 100);
      };

      wsRef.current.onmessage = handleMessage;

      wsRef.current.onclose = (event) => {
        setIsConnected(false);
        setIsConnecting(false);
        log.log("WebSocket disconnected from server console", {
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean,
        });
      };

      wsRef.current.onerror = (error) => {
        setIsConnecting(false);
        log.error("WebSocket error:", error);
        log.log(
          "WebSocket state when error occurred:",
          wsRef.current?.readyState
        );
      };
    } catch (error) {
      setIsConnecting(false);
      log.error("Failed to create WebSocket connection:", error);
    }
  }, [
    serverId,
    token,
    filterRcon,
    buildWebSocketUrl,
    sendFilterUpdate,
    handleMessage,
  ]);

  // 断开WebSocket连接
  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
      setIsConnected(false);
      setIsConnecting(false);
      log.log("WebSocket connection manually closed");
    }
  }, []);

  // 当过滤开关变化时，发送设置到后端并请求刷新日志
  useEffect(() => {
    const prevFilterRcon = prevFilterRconRef.current;

    // 只有在连接建立且filter值真正改变时才处理
    if (isConnected && prevFilterRcon !== filterRcon) {
      log.log("Filter setting changed, updating backend and refreshing logs", {
        from: prevFilterRcon,
        to: filterRcon,
      });
      sendFilterUpdate(filterRcon);
      // 短暂延迟后请求刷新，确保后端已处理过滤设置
      setTimeout(() => {
        requestLogRefresh();
      }, 100);
    }

    // 更新上一次的值
    prevFilterRconRef.current = filterRcon;
  }, [filterRcon, isConnected, sendFilterUpdate, requestLogRefresh]);

  // 清理函数
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    isConnecting,
    connect,
    disconnect,
    sendCommand,
    sendFilterUpdate,
    requestLogRefresh,
  };
}
