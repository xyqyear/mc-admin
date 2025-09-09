import { useEffect, useRef, useState, useCallback } from 'react';
import { useTokenStore } from '@/stores/useTokenStore';
import { getApiBaseUrl } from '@/utils/api';

// WebSocket消息类型
export interface WebSocketMessage {
  type: 'log' | 'error' | 'info' | 'logs_refreshed';
  content?: string;
  message?: string;
  filter_rcon?: boolean;
}

// WebSocket连接状态
export type ConnectionState = 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'ERROR' | 'RETRYING';

// 重试配置常量
const MAX_RETRY_COUNT = 5;
const RETRY_DELAYS = [1000, 2000, 4000, 8000, 16000]; // 指数退避延迟

export interface UseServerConsoleWebSocketReturn {
  connectionState: ConnectionState;
  lastError: string | null;
  filterRcon: boolean;
  connect: () => void;
  disconnect: () => void;
  sendCommand: (command: string) => void;
  setFilterRcon: (enabled: boolean) => void;
  requestLogRefresh: () => void;
  onMessage: (callback: (message: WebSocketMessage) => void) => void;
  removeMessageListener: (callback: (message: WebSocketMessage) => void) => void;
}

export const useServerConsoleWebSocket = (
  serverId: string,
  canConnect: boolean = true
): UseServerConsoleWebSocketReturn => {
  const { token } = useTokenStore();

  // WebSocket refs
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const retryCountRef = useRef(0);
  const messageCallbacksRef = useRef<Set<(message: WebSocketMessage) => void>>(new Set());

  // State
  const [connectionState, setConnectionState] = useState<ConnectionState>('DISCONNECTED');
  const [filterRcon, setFilterRconState] = useState(true);
  const [lastError, setLastError] = useState<string | null>(null);

  // Use refs to break circular dependencies
  const connectWebSocketRef = useRef<() => void>();
  const scheduleReconnectRef = useRef<() => void>();

  // 构建WebSocket URL
  const buildWebSocketUrl = useCallback(() => {
    if (!serverId || !token) return null;
    const baseUrl = getApiBaseUrl(true); // true for WebSocket
    return `${baseUrl}/servers/${serverId}/console?token=${encodeURIComponent(token)}`;
  }, [serverId, token]);

  // 断开WebSocket
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      // 避免触发onclose事件导致重连
      const ws = wsRef.current;
      wsRef.current = null;

      // 移除事件监听器以避免竞争条件
      ws.onopen = null;
      ws.onmessage = null;
      ws.onclose = null;
      ws.onerror = null;

      // 如果连接还在进行中，直接关闭
      if (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN) {
        ws.close(1000); // 正常关闭
      }
    }

    setConnectionState('DISCONNECTED');
  }, []);

  // WebSocket消息处理
  const handleWebSocketMessage = useCallback((event: MessageEvent) => {
    try {
      const message: WebSocketMessage = JSON.parse(event.data);
      
      // 调用所有注册的回调函数
      messageCallbacksRef.current.forEach(callback => {
        callback(message);
      });

      // 处理特定的消息类型
      switch (message.type) {
        case 'error':
          if (message.message) {
            setLastError(message.message);
            // 错误时断开连接并重试
            disconnect();
            if (scheduleReconnectRef.current) {
              scheduleReconnectRef.current();
            }
          }
          break;
      }
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
    }
  }, [disconnect]);

  // 发送过滤设置更新
  const sendFilterUpdate = useCallback((newFilterRcon: boolean) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }

    try {
      wsRef.current.send(JSON.stringify({
        type: 'set_filter',
        filter_rcon: newFilterRcon,
      }));
    } catch (error) {
      console.error('Failed to send filter update:', error);
    }
  }, []);

  // 连接WebSocket
  const connect = useCallback(() => {
    // 如果已经有连接在进行中或已连接，先断开
    if (wsRef.current && (wsRef.current.readyState === WebSocket.CONNECTING || wsRef.current.readyState === WebSocket.OPEN)) {
      disconnect();
    }

    if (!canConnect || !token || !serverId) {
      return;
    }

    const wsUrl = buildWebSocketUrl();
    if (!wsUrl) {
      console.error('Failed to build WebSocket URL');
      return;
    }

    setConnectionState('CONNECTING');
    setLastError(null);

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws; // 立即设置引用

      ws.onopen = () => {
        // 检查连接是否仍然有效
        if (wsRef.current !== ws) {
          ws.close();
          return;
        }

        console.log('WebSocket connected');
        setConnectionState('CONNECTED');
        retryCountRef.current = 0;

        // 发送初始过滤设置
        setTimeout(() => {
          if (wsRef.current === ws && ws.readyState === WebSocket.OPEN) {
            sendFilterUpdate(filterRcon);
          }
        }, 100);
      };

      ws.onmessage = handleWebSocketMessage;

      ws.onclose = (event) => {
        // 检查这是否是当前活动的连接
        if (wsRef.current !== ws) {
          return;
        }

        console.log('WebSocket disconnected:', event.code, event.reason);
        wsRef.current = null;
        setConnectionState('DISCONNECTED');

        // 如果不是手动断开，尝试重连
        if (event.code !== 1000 && event.code !== 1001) {
          if (scheduleReconnectRef.current) {
            scheduleReconnectRef.current();
          }
        }
      };

      ws.onerror = (error) => {
        // 检查这是否是当前活动的连接
        if (wsRef.current !== ws) {
          return;
        }

        console.error('WebSocket error:', error);
        setConnectionState('ERROR');
        setLastError('WebSocket connection error');
      };

    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      setConnectionState('ERROR');
      setLastError('Failed to create WebSocket connection');
    }
  }, [canConnect, token, serverId, buildWebSocketUrl, filterRcon, sendFilterUpdate, handleWebSocketMessage, disconnect]);

  const scheduleReconnect = useCallback(() => {
    if (retryCountRef.current >= MAX_RETRY_COUNT) {
      setConnectionState('ERROR');
      setLastError(`Maximum retry attempts (${MAX_RETRY_COUNT}) exceeded`);
      return;
    }

    const delay = RETRY_DELAYS[Math.min(retryCountRef.current, RETRY_DELAYS.length - 1)];
    retryCountRef.current++;

    setConnectionState('RETRYING');

    reconnectTimeoutRef.current = setTimeout(() => {
      if (connectWebSocketRef.current) {
        connectWebSocketRef.current();
      }
    }, delay);
  }, []);

  // Update refs after callbacks are defined
  connectWebSocketRef.current = connect;
  scheduleReconnectRef.current = scheduleReconnect;

  // 发送命令
  const sendCommand = useCallback((command: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !command.trim()) {
      return;
    }

    try {
      wsRef.current.send(JSON.stringify({
        type: 'command',
        command: command.trim(),
      }));
    } catch (error) {
      console.error('Failed to send command:', error);
    }
  }, []);

  // 请求刷新日志
  const requestLogRefresh = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }

    try {
      wsRef.current.send(JSON.stringify({
        type: 'refresh_logs',
      }));
    } catch (error) {
      console.error('Failed to request log refresh:', error);
    }
  }, []);

  // 设置过滤器
  const setFilterRcon = useCallback((enabled: boolean) => {
    setFilterRconState(enabled);
    sendFilterUpdate(enabled);

    // 延迟请求刷新日志
    setTimeout(() => {
      requestLogRefresh();
    }, 100);
  }, [sendFilterUpdate, requestLogRefresh]);

  // 注册消息监听器
  const onMessage = useCallback((callback: (message: WebSocketMessage) => void) => {
    messageCallbacksRef.current.add(callback);
  }, []);

  // 移除消息监听器
  const removeMessageListener = useCallback((callback: (message: WebSocketMessage) => void) => {
    messageCallbacksRef.current.delete(callback);
  }, []);

  // 管理WebSocket连接
  useEffect(() => {
    let mounted = true;

    if (canConnect) {
      // 使用setTimeout避免在快速状态变化时立即重连
      const timeoutId = setTimeout(() => {
        if (mounted) {
          connect();
        }
      }, 100);

      return () => {
        mounted = false;
        clearTimeout(timeoutId);
        disconnect();
      };
    } else {
      disconnect();
    }

    return () => {
      mounted = false;
      disconnect();
    };
  }, [canConnect, connect, disconnect]);

  // 当服务器ID变化时重置状态
  useEffect(() => {
    retryCountRef.current = 0;
    setLastError(null);
  }, [serverId]);

  return {
    connectionState,
    lastError,
    filterRcon,
    connect,
    disconnect,
    sendCommand,
    setFilterRcon,
    requestLogRefresh,
    onMessage,
    removeMessageListener,
  };
};