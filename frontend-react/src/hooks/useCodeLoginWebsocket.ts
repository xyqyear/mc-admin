import { useTokenStore } from "@/stores/useTokenStore";
import { getApiBaseUrl } from "@/utils/api";
import { App } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

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

export enum ConnectionStatus {
  IDLE = "idle",
  CONNECTING = "connecting",
  CONNECTED = "connected",
  ERROR = "error",
}

export const useCodeLoginWebsocket = () => {
  const [code, setCode] = useState("加载中");
  const [countdown, setCountdown] = useState(0);
  const [codeTimeout, setCodeTimeout] = useState(0);
  const [status, setStatus] = useState<ConnectionStatus>(ConnectionStatus.IDLE);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const countdownRef = useRef<NodeJS.Timeout | null>(null);
  const { setToken } = useTokenStore();
  const { message } = App.useApp();
  const navigate = useNavigate();

  const wsBaseUrl = getApiBaseUrl(true).replace(/\/$/, "");

  const cleanup = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close(1000);
      wsRef.current = null;
    }
    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    cleanup();
    setStatus(ConnectionStatus.IDLE);
    setError(null);
    setCode("加载中");
    setCountdown(0);
    setCodeTimeout(0);
  }, [cleanup]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setError(null);
    setCode("连接中...");
    setStatus(ConnectionStatus.CONNECTING);

    try {
      wsRef.current = new WebSocket(`${wsBaseUrl}/auth/code`);

      wsRef.current.onopen = () => {
        setStatus(ConnectionStatus.CONNECTED);
        setError(null);
      };

      wsRef.current.onmessage = (event) => {
        if (event.data === "pong") return;

        try {
          const data: ServerMessage = JSON.parse(event.data);
          if (data.type === "code") {
            setCode(data.code);
            setCodeTimeout(data.timeout);
            setCountdown(data.timeout);
          } else if (data.type === "verified") {
            setToken(data.access_token);
            message.success("验证成功，正在跳转...");
            disconnect();
            navigate("/");
          }
        } catch (error) {
          console.error("Failed to parse WebSocket message:", error);
          setError("消息解析失败");
          setStatus(ConnectionStatus.ERROR);
        }
      };

      wsRef.current.onclose = (event) => {
        if (event.code === 1000 || event.code === 1001 || event.code === 1006) {
          setStatus(ConnectionStatus.IDLE);
        } else {
          setError("连接已断开");
          setStatus(ConnectionStatus.ERROR);
        }
      };

      wsRef.current.onerror = () => {
        setError("连接失败，请检查网络");
        setStatus(ConnectionStatus.ERROR);
      };
    } catch (err) {
      console.error("WebSocket connection failed:", err);
      setError("无法建立连接");
      setStatus(ConnectionStatus.ERROR);
    }
  }, [wsBaseUrl, setToken, message, navigate, disconnect]);

  useEffect(() => {
    if (status === ConnectionStatus.CONNECTED && countdown > 0) {
      countdownRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            if (countdownRef.current) {
              clearInterval(countdownRef.current);
              countdownRef.current = null;
            }
            setError("验证码已过期，请重新获取");
            setStatus(ConnectionStatus.ERROR);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }

    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    };
  }, [status, countdown]);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  const connected = status === ConnectionStatus.CONNECTED;
  const isConnecting = status === ConnectionStatus.CONNECTING;
  const hasError = status === ConnectionStatus.ERROR;

  return {
    code,
    countdown,
    codeTimeout,
    connected,
    isConnecting,
    hasError,
    error,
    status,
    connect,
    disconnect,
  };
};
