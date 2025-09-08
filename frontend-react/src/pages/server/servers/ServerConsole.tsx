import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Switch, Button, Space, Alert, Typography, Spin } from 'antd';
import { ReloadOutlined, DisconnectOutlined, LinkOutlined, CodeOutlined } from '@ant-design/icons';
import { useXTerm } from 'react-xtermjs';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';

import { useServerQueries } from '@/hooks/queries/base/useServerQueries';
import { useTokenStore } from '@/stores/useTokenStore';
import { getApiBaseUrl } from '@/utils/api';
import { Terminal } from '@xterm/xterm';
import PageHeader from '@/components/layout/PageHeader';
import LoadingSpinner from '@/components/layout/LoadingSpinner';

const { Text } = Typography;

// WebSocket消息类型
interface WebSocketMessage {
  type: 'log' | 'error' | 'info' | 'logs_refreshed';
  content?: string;
  message?: string;
  filter_rcon?: boolean;
}

// WebSocket连接状态
type ConnectionState = 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'ERROR' | 'RETRYING';

// 重试配置常量
const MAX_RETRY_COUNT = 5;
const RETRY_DELAYS = [1000, 2000, 4000, 8000, 16000]; // 指数退避延迟

const ServerConsole: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const serverId = id!;
  const { token } = useTokenStore();

  // React Query hooks
  const { useServerStatus, useServerInfo } = useServerQueries();
  const { data: serverStatus } = useServerStatus(serverId);
  const { data: serverInfo, isLoading: serverInfoLoading, isError: serverInfoError } = useServerInfo(serverId);

  // WebSocket refs
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const retryCountRef = useRef(0);

  // Terminal instance ref - 用于打破循环依赖
  const terminalInstanceRef = useRef<Terminal | null>(null);

  // State
  const [connectionState, setConnectionState] = useState<ConnectionState>('DISCONNECTED');
  const [filterRcon, setFilterRcon] = useState(true);
  const [currentCommand, setCurrentCommand] = useState('');
  const [lastError, setLastError] = useState<string | null>(null);

  // XTerm 配置 - 使用useMemo来避免每次渲染重新创建
  const terminalOptions = useMemo(() => ({
    theme: {
      background: '#000000',
      foreground: '#ffffff',
      cursor: '#ffffff',
    },
    fontFamily: 'Consolas, "Courier New", monospace',
    fontSize: 14,
    cursorBlink: true,
    convertEol: true,
    disableStdin: false,
  }), []);

  const terminalAddons = useMemo(() => [new FitAddon(), new WebLinksAddon()], []);

  // 获取FitAddon引用
  const fitAddon = terminalAddons[0] as FitAddon;

  // 使用 useXTerm 钩子
  const terminal = useXTerm({
    options: terminalOptions,
    addons: terminalAddons,
  });

  // 同步terminal实例到ref
  useEffect(() => {
    terminalInstanceRef.current = terminal.instance;
  }, [terminal.instance]);

  // 创建稳定的terminal访问器
  const getTerminal = useCallback(() => terminalInstanceRef.current, []);

  // 处理终端数据输入 - 使用稳定的访问器
  const handleTerminalData = useCallback((data: string) => {
    const terminalInstance = getTerminal();

    // 处理回车键
    if (data === '\r') {
      if (currentCommand.trim()) {
        // 发送命令
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          try {
            wsRef.current.send(JSON.stringify({
              type: 'command',
              command: currentCommand.trim(),
            }));
          } catch (error) {
            console.error('Failed to send command:', error);
            if (terminalInstance) {
              terminalInstance.write('\x1b[31mFailed to send command\x1b[0m\r\n');
            }
          }
        }
        setCurrentCommand('');
      }
      if (terminalInstance) {
        terminalInstance.write('\r\n');
      }
      return;
    }

    // 处理退格键
    if (data === '\x7f') {
      if (currentCommand.length > 0) {
        setCurrentCommand(prev => prev.slice(0, -1));
        if (terminalInstance) {
          terminalInstance.write('\b \b');
        }
      }
      return;
    }

    // 处理 ESC
    if (data === '\x1b') {
      setCurrentCommand('');
      if (terminalInstance) {
        terminalInstance.write('^C\r\n');
      }
      return;
    }

    // 处理普通字符
    if (data >= ' ' || data === '\t') {
      setCurrentCommand(prev => prev + data);
      if (terminalInstance) {
        terminalInstance.write(data);
      }
    }
  }, [currentCommand, getTerminal]); // 使用稳定的getTerminal

  // 设置终端数据监听器 - 使用稳定的引用
  useEffect(() => {
    if (terminal.instance) {
      const disposable = terminal.instance.onData(handleTerminalData);
      return () => {
        disposable?.dispose();
      };
    }
  }, [terminal.instance, handleTerminalData]);

  // 自动调整终端大小
  useEffect(() => {
    if (fitAddon && terminal.instance) {
      setTimeout(() => fitAddon.fit(), 0);

      const handleResize = () => {
        fitAddon.fit();
      };

      window.addEventListener('resize', handleResize);
      return () => {
        window.removeEventListener('resize', handleResize);
      };
    }
  }, [fitAddon, terminal.instance, serverId]);

  // 检查服务器状态是否允许WebSocket连接
  const canConnectWebSocket = useCallback(() => {
    if (!serverStatus) return false;
    return serverStatus !== 'REMOVED' && serverStatus !== 'EXISTS';
  }, [serverStatus]);

  // 构建WebSocket URL
  const buildWebSocketUrl = useCallback(() => {
    if (!serverId || !token) return null;
    const baseUrl = getApiBaseUrl(true); // true for WebSocket
    return `${baseUrl}/servers/${serverId}/console?token=${encodeURIComponent(token)}`;
  }, [serverId, token]);

  // 断开WebSocket
  const disconnectWebSocket = useCallback(() => {
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

  // Use refs to break circular dependencies
  const connectWebSocketRef = useRef<() => void>();
  const scheduleReconnectRef = useRef<() => void>();

  // WebSocket消息处理 - 使用稳定的访问器
  const handleWebSocketMessage = useCallback((event: MessageEvent) => {
    const terminalInstance = getTerminal();
    if (!terminalInstance) return;

    try {
      const message: WebSocketMessage = JSON.parse(event.data);

      switch (message.type) {
        case 'log':
          if (message.content) {
            terminalInstance.write(message.content);
          }
          break;

        case 'logs_refreshed':
          if (message.content !== undefined) {
            terminalInstance.write(message.content);
          }
          break;

        case 'error':
          if (message.message) {
            terminalInstance.write(`\x1b[31mError: ${message.message}\x1b[0m\r\n`);
            setLastError(message.message);
            // 错误时断开连接并重试
            disconnectWebSocket();
            if (scheduleReconnectRef.current) {
              scheduleReconnectRef.current();
            }
          }
          break;

        case 'info':
          if (message.message) {
            terminalInstance.write(`\x1b[36mInfo: ${message.message}\x1b[0m\r\n`);
          }
          break;
      }
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
    }
  }, [getTerminal, disconnectWebSocket]); // 使用稳定的getTerminal

  // 清屏 - 使用稳定的访问器
  const handleClearScreen = useCallback(() => {
    const terminalInstance = getTerminal();
    if (terminalInstance) {
      terminalInstance.clear();
    }
  }, [getTerminal]); // 使用稳定的getTerminal

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
  const connectWebSocket = useCallback(() => {
    // 如果已经有连接在进行中或已连接，先断开
    if (wsRef.current && (wsRef.current.readyState === WebSocket.CONNECTING || wsRef.current.readyState === WebSocket.OPEN)) {
      disconnectWebSocket();
    }

    if (!canConnectWebSocket() || !token || !serverId) {
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

        // 使用稳定的访问器
        const terminalInstance = getTerminal();
        if (terminalInstance) {
          handleClearScreen();
          terminalInstance.write('\x1b[32mConnected to server console\x1b[0m\r\n');
        }

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

        // 使用稳定的访问器
        const terminalInstance = getTerminal();
        if (terminalInstance) {
          terminalInstance.write('\x1b[33mDisconnected from server console\x1b[0m\r\n');
        }

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

        // 使用稳定的访问器
        const terminalInstance = getTerminal();
        if (terminalInstance) {
          terminalInstance.write('\x1b[31mConnection error\x1b[0m\r\n');
        }
      };

    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      setConnectionState('ERROR');
      setLastError('Failed to create WebSocket connection');
    }
  }, [canConnectWebSocket, token, serverId, buildWebSocketUrl, filterRcon, sendFilterUpdate, handleWebSocketMessage, getTerminal, disconnectWebSocket, handleClearScreen]);

  // 安排重连 - 使用稳定的访问器
  const scheduleReconnect = useCallback(() => {
    if (retryCountRef.current >= MAX_RETRY_COUNT) {
      setConnectionState('ERROR');
      setLastError(`Maximum retry attempts (${MAX_RETRY_COUNT}) exceeded`);
      return;
    }

    const delay = RETRY_DELAYS[Math.min(retryCountRef.current, RETRY_DELAYS.length - 1)];
    retryCountRef.current++;

    setConnectionState('RETRYING');

    // 使用稳定的访问器
    const terminalInstance = getTerminal();
    if (terminalInstance) {
      terminalInstance.write(`\x1b[33mRetrying connection in ${delay / 1000}s... (${retryCountRef.current}/${MAX_RETRY_COUNT})\x1b[0m\r\n`);
    }

    reconnectTimeoutRef.current = setTimeout(() => {
      if (connectWebSocketRef.current) {
        connectWebSocketRef.current();
      }
    }, delay);
  }, [getTerminal]); // 使用稳定的getTerminal

  // Update refs after callbacks are defined
  connectWebSocketRef.current = connectWebSocket;
  scheduleReconnectRef.current = scheduleReconnect;

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

  // 处理过滤开关变化
  const handleFilterChange = useCallback((checked: boolean) => {
    setFilterRcon(checked);
    sendFilterUpdate(checked);

    // 延迟请求刷新日志
    setTimeout(() => {
      requestLogRefresh();
    }, 100);
  }, [sendFilterUpdate, requestLogRefresh]);

  // 手动重连
  const handleManualReconnect = useCallback(() => {
    retryCountRef.current = 0;
    disconnectWebSocket();
    setTimeout(() => {
      connectWebSocket();
    }, 100);
  }, [disconnectWebSocket, connectWebSocket]);


  // 管理WebSocket连接
  useEffect(() => {
    let mounted = true;

    if (canConnectWebSocket()) {
      // 使用setTimeout避免在快速状态变化时立即重连
      const timeoutId = setTimeout(() => {
        if (mounted) {
          connectWebSocket();
        }
      }, 100);

      return () => {
        mounted = false;
        clearTimeout(timeoutId);
        disconnectWebSocket();
      };
    } else {
      disconnectWebSocket();
    }

    return () => {
      mounted = false;
      disconnectWebSocket();
    };
  }, [canConnectWebSocket, connectWebSocket, disconnectWebSocket]);

  // 当服务器ID变化时重置状态
  useEffect(() => {
    retryCountRef.current = 0;
    setLastError(null);
    setCurrentCommand('');
    handleClearScreen();
  }, [serverId, handleClearScreen]);

  // 获取连接状态显示
  const getConnectionStatus = () => {
    switch (connectionState) {
      case 'CONNECTED':
        return { text: '已连接', color: 'success', icon: <LinkOutlined /> };
      case 'CONNECTING':
        return { text: '正在连接...', color: 'processing', icon: <Spin size="small" /> };
      case 'RETRYING':
        return { text: `正在重试... (${retryCountRef.current}/${MAX_RETRY_COUNT})`, color: 'warning', icon: <Spin size="small" /> };
      case 'ERROR':
        return { text: '连接错误', color: 'error', icon: <DisconnectOutlined /> };
      default:
        return { text: '已断开连接', color: 'default', icon: <DisconnectOutlined /> };
    }
  };

  const connectionStatus = getConnectionStatus();


  // 如果没有服务器ID，返回错误
  if (!id) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert
          message="参数错误"
          description="缺少服务器ID参数"
          type="error"
          action={
            <Button size="small" onClick={() => navigate('/overview')}>
              返回概览
            </Button>
          }
        />
      </div>
    )
  }

  // 错误状态
  if (serverInfoError) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert
          message="加载失败"
          description={`无法加载服务器 "${id}" 的信息`}
          type="error"
          action={
            <Button size="small" onClick={() => navigate('/overview')}>
              返回概览
            </Button>
          }
        />
      </div>
    )
  }

  // 加载状态
  if (serverInfoLoading || !serverInfo) {
    return <LoadingSpinner height="16rem" tip="加载服务器信息中..." />
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex-none space-y-4">
        <PageHeader
          title="控制台"
          icon={<CodeOutlined />}
          serverTag={serverInfo.name}
          actions={
            <>
              <div className="flex items-center space-x-2">
                <Text type="secondary">状态:</Text>
                <Space size="small">
                  {connectionStatus.icon}
                  <Text type={connectionStatus.color as any}>{connectionStatus.text}</Text>
                </Space>
              </div>
              <Switch
                checked={filterRcon}
                onChange={handleFilterChange}
                checkedChildren="过滤RCON"
                unCheckedChildren="展示所有"
                disabled={connectionState === 'CONNECTING'}
              />
              <Button
                icon={<ReloadOutlined />}
                onClick={handleManualReconnect}
                disabled={connectionState === 'CONNECTING'}
                type="primary"
              >
                重新连接
              </Button>
              <Button onClick={handleClearScreen}>
                清屏
              </Button>
            </>
          }
        />

        {lastError && (
          <Alert
            message="连接错误"
            description={lastError}
            type="error"
            showIcon
            closable
            onClose={() => setLastError(null)}
          />
        )}

        {!canConnectWebSocket() && (
          <Alert
            message="控制台不可用"
            description={`控制台仅在服务器状态不是 REMOVED 或 EXISTS 时可用。当前状态: ${serverStatus}`}
            type="info"
            showIcon
          />
        )}
      </div>

      <Card className="flex-1 min-h-0 mt-4" styles={{ body: { height: '100%', width: '100%' } }}>
        <div
          ref={terminal.ref as React.LegacyRef<HTMLDivElement>}
          className="h-full w-full"
          style={{ minHeight: '400px' }}
        />
      </Card>
    </div>
  );
};

export default ServerConsole;