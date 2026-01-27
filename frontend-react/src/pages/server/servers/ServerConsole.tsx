import React, { useEffect, useRef, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Button, Space, Typography, Spin } from 'antd';
import { ReloadOutlined, DisconnectOutlined, LinkOutlined, CodeOutlined, ExclamationCircleOutlined, LoadingOutlined } from '@ant-design/icons';

import { useServerQueries } from '@/hooks/queries/base/useServerQueries';
import { useServerConsoleWebSocket } from '@/hooks/useServerConsoleWebSocket';
import PageHeader from '@/components/layout/PageHeader';
import ServerOperationButtons from '@/components/server/ServerOperationButtons';
import ServerTerminal, { ServerTerminalRef } from '@/components/server/ServerTerminal';
import ServerStateTag from '@/components/overview/ServerStateTag';

const { Text } = Typography;

type ConsoleStatus =
  | { type: 'loading' }
  | { type: 'error'; message: string }
  | { type: 'unavailable'; reason: React.ReactNode }
  | { type: 'disconnected' }
  | { type: 'connecting' }
  | { type: 'connected' }
  | { type: 'retrying' }
  | { type: 'connection_error'; message: string };

const ServerConsole: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const serverId = id || '';
  // Terminal ref
  const terminalRef = useRef<ServerTerminalRef>(null);

  // React Query hooks
  const { useServerStatus, useServerInfo } = useServerQueries();
  const { data: serverStatus } = useServerStatus(serverId);
  const { data: serverInfo, isLoading: serverInfoLoading, isError: serverInfoError } = useServerInfo(serverId);

  // Check if server status allows WebSocket connection
  const canConnectWebSocket = useMemo(() => {
    if (!serverStatus || !id || serverInfoLoading || serverInfoError) return false;
    return serverStatus !== 'REMOVED' && serverStatus !== 'EXISTS';
  }, [serverStatus, id, serverInfoLoading, serverInfoError]);

  // WebSocket hook
  const {
    connectionState,
    lastError,
    sendInput,
    sendResize,
    onMessage,
    connect,
    disconnect
  } = useServerConsoleWebSocket(serverId, false);

  // Determine console status for header display
  const consoleStatus: ConsoleStatus = useMemo(() => {
    if (!id) {
      return { type: 'error', message: '缺少服务器ID' };
    }
    if (serverInfoLoading) {
      return { type: 'loading' };
    }
    if (serverInfoError) {
      return { type: 'error', message: `无法加载服务器 "${serverId}"` };
    }
    if (serverStatus && !canConnectWebSocket) {
      return { type: 'unavailable', reason: <ServerStateTag state={serverStatus} /> };
    }
    if (lastError) {
      return { type: 'connection_error', message: lastError };
    }
    switch (connectionState) {
      case 'CONNECTED':
        return { type: 'connected' };
      case 'CONNECTING':
        return { type: 'connecting' };
      case 'RETRYING':
        return { type: 'retrying' };
      case 'ERROR':
        return { type: 'connection_error', message: '连接失败' };
      default:
        return { type: 'disconnected' };
    }
  }, [id, serverInfoLoading, serverInfoError, serverId, serverStatus, canConnectWebSocket, lastError, connectionState]);

  // Get status display info (memoized)
  const statusDisplay = useMemo(() => {
    switch (consoleStatus.type) {
      case 'loading':
        return { text: '加载中...', color: 'secondary', icon: <LoadingOutlined /> };
      case 'error':
        return { text: consoleStatus.message, color: 'danger', icon: <ExclamationCircleOutlined /> };
      case 'unavailable':
        return { text: consoleStatus.reason, color: 'warning', icon: null };
      case 'connected':
        return { text: '已连接', color: 'success', icon: <LinkOutlined /> };
      case 'connecting':
        return { text: '连接中...', color: 'secondary', icon: <Spin size="small" /> };
      case 'retrying':
        return { text: '重试中...', color: 'warning', icon: <Spin size="small" /> };
      case 'connection_error':
        return { text: consoleStatus.message, color: 'danger', icon: <DisconnectOutlined /> };
      default:
        return { text: '已断开', color: 'secondary', icon: <DisconnectOutlined /> };
    }
  }, [consoleStatus]);

  // Terminal ready handler
  const handleTerminalReady = useCallback((terminal: ServerTerminalRef) => {
    onMessage((message) => {
      if (terminal.onMessage) {
        terminal.onMessage(message);
      }
    });

    if (canConnectWebSocket) {
      const size = terminal.getSize();
      if (size) {
        connect(size.cols, size.rows);
      }
    }
  }, [onMessage, canConnectWebSocket, connect]);

  // Handle terminal input
  const handleSendInput = useCallback((data: string) => {
    sendInput(data);
  }, [sendInput]);

  // Handle terminal resize
  const handleTerminalResize = useCallback((cols: number, rows: number) => {
    sendResize(cols, rows);
  }, [sendResize]);

  // Manual reconnect
  const handleManualReconnect = useCallback(() => {
    disconnect();
    const size = terminalRef.current?.getSize();
    if (size) {
      connect(size.cols, size.rows);
    }
  }, [disconnect, connect]);

  // Clear screen
  const handleClearScreen = useCallback(() => {
    if (terminalRef.current) {
      terminalRef.current.clear();
    }
  }, []);

  // Connection state messages in terminal
  useEffect(() => {
    if (connectionState === 'CONNECTED' && terminalRef.current) {
      terminalRef.current.clear();
      terminalRef.current.write('\x1b[32m已连接到服务器控制台\x1b[0m\r\n');
    } else if (connectionState === 'DISCONNECTED' && terminalRef.current) {
      terminalRef.current.write('\x1b[33m已断开与服务器控制台的连接\x1b[0m\r\n');
    } else if (connectionState === 'ERROR' && terminalRef.current) {
      terminalRef.current.write('\x1b[31m连接错误\x1b[0m\r\n');
    } else if (connectionState === 'RETRYING' && terminalRef.current) {
      terminalRef.current.write('\x1b[33m正在重试连接...\x1b[0m\r\n');
    }
  }, [connectionState]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  const canReconnect = canConnectWebSocket &&
                       consoleStatus.type !== 'loading' &&
                       consoleStatus.type !== 'error' &&
                       consoleStatus.type !== 'connecting';

  return (
    <div className="h-full flex flex-col space-y-4">
      <PageHeader
        title="控制台"
        icon={<CodeOutlined />}
        serverTag={serverInfo?.name}
        actions={
          serverInfo && (
            <ServerOperationButtons
              serverId={serverId}
              serverName={serverInfo.name}
              status={serverStatus}
            />
          )
        }
      />

      <Card
        className="flex-1 min-h-0 flex flex-col"
        classNames={{ body: "flex flex-col flex-1 !p-4" }}
        title={
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-2">
              <Text type="secondary">状态:</Text>
              {consoleStatus.type === 'unavailable' ? (
                statusDisplay.text
              ) : (
                <Space size="small">
                  {statusDisplay.icon}
                  <Text type={statusDisplay.color as any}>{statusDisplay.text}</Text>
                </Space>
              )}
              {consoleStatus.type === 'error' && (
                <Button
                  size="small"
                  type="link"
                  onClick={() => navigate('/overview')}
                >
                  返回概览
                </Button>
              )}
            </div>
            <div className="flex items-center space-x-2">
              <Button
                icon={<ReloadOutlined />}
                onClick={handleManualReconnect}
                disabled={!canReconnect}
                type="primary"
                size="small"
              >
                重新连接
              </Button>
              <Button onClick={handleClearScreen} size="small">
                清屏
              </Button>
            </div>
          </div>
        }
      >
        <ServerTerminal
          key={serverId}
          ref={terminalRef}
          onSendInput={handleSendInput}
          onReady={handleTerminalReady}
          onResize={handleTerminalResize}
          className="h-full"
        />
      </Card>
    </div>
  );
};

export default ServerConsole;
