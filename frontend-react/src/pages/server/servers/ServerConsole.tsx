import React, { useEffect, useRef, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Terminal,
  RotateCw,
  Unplug,
  Link,
  AlertCircle,
  Loader2,
} from 'lucide-react';

import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { useServerQueries } from '@/hooks/queries/base/useServerQueries';
import { useServerConsoleWebSocket, WebSocketMessage } from '@/hooks/useServerConsoleWebSocket';
import PageHeader from '@/components/layout/PageHeader';
import ServerOperationButtons from '@/components/server/ServerOperationButtons';
import ServerTerminal, { ServerTerminalRef } from '@/components/server/ServerTerminal';
import ServerStateTag from '@/components/overview/ServerStateTag';

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
  const terminalRef = useRef<ServerTerminalRef>(null);

  const { useServerStatus, useServerInfo } = useServerQueries();
  const { data: serverStatus } = useServerStatus(serverId);
  const { data: serverInfo, isLoading: serverInfoLoading, isError: serverInfoError } = useServerInfo(serverId);

  const canConnectWebSocket = useMemo(() => {
    if (!serverStatus || !id || serverInfoLoading || serverInfoError) return false;
    return serverStatus !== 'REMOVED' && serverStatus !== 'EXISTS';
  }, [serverStatus, id, serverInfoLoading, serverInfoError]);

  const {
    connectionState,
    lastError,
    sendInput,
    sendResize,
    onMessage,
    removeMessageListener,
    connect,
    disconnect
  } = useServerConsoleWebSocket(serverId, false);

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

  const statusDisplay = useMemo(() => {
    switch (consoleStatus.type) {
      case 'loading':
        return {
          text: '加载中...',
          className: 'text-muted-foreground',
          icon: <Loader2 className="h-4 w-4 animate-spin" />,
        };
      case 'error':
        return {
          text: consoleStatus.message,
          className: 'text-destructive',
          icon: <AlertCircle className="h-4 w-4" />,
        };
      case 'unavailable':
        return {
          text: consoleStatus.reason,
          className: 'text-yellow-600',
          icon: null,
        };
      case 'connected':
        return {
          text: '已连接',
          className: 'text-green-600',
          icon: <Link className="h-4 w-4" />,
        };
      case 'connecting':
        return {
          text: '连接中...',
          className: 'text-muted-foreground',
          icon: <Spinner className="size-4" />,
        };
      case 'retrying':
        return {
          text: '重试中...',
          className: 'text-yellow-600',
          icon: <Spinner className="size-4" />,
        };
      case 'connection_error':
        return {
          text: consoleStatus.message,
          className: 'text-destructive',
          icon: <Unplug className="h-4 w-4" />,
        };
      default:
        return {
          text: '已断开',
          className: 'text-muted-foreground',
          icon: <Unplug className="h-4 w-4" />,
        };
    }
  }, [consoleStatus]);

  const handleTerminalReady = useCallback((terminal: ServerTerminalRef) => {
    if (canConnectWebSocket) {
      const size = terminal.getSize();
      if (size) {
        connect(size.cols, size.rows);
      }
    }
  }, [canConnectWebSocket, connect]);

  useEffect(() => {
    const handleMessage = (message: WebSocketMessage) => {
      terminalRef.current?.onMessage?.(message);
    };

    onMessage(handleMessage);

    return () => {
      removeMessageListener(handleMessage);
    };
  }, [onMessage, removeMessageListener]);

  const handleSendInput = useCallback((data: string) => {
    sendInput(data);
  }, [sendInput]);

  const handleTerminalResize = useCallback((cols: number, rows: number) => {
    sendResize(cols, rows);
  }, [sendResize]);

  const handleManualReconnect = useCallback(() => {
    disconnect();
    const size = terminalRef.current?.getSize();
    if (size) {
      connect(size.cols, size.rows);
    }
  }, [disconnect, connect]);

  const handleClearScreen = useCallback(() => {
    if (terminalRef.current) {
      terminalRef.current.clear();
    }
  }, []);

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
    <div className="h-full overflow-hidden flex flex-col space-y-4">
      <PageHeader
        title="控制台"
        icon={<Terminal className="h-5 w-5" />}
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

      <Card className="flex-1 min-h-0 flex flex-col">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-2">
              <span className="text-sm text-muted-foreground">状态:</span>
              {consoleStatus.type === 'unavailable' ? (
                statusDisplay.text
              ) : (
                <div className="flex items-center gap-1.5">
                  {statusDisplay.icon}
                  <span className={`text-sm ${statusDisplay.className}`}>{statusDisplay.text}</span>
                </div>
              )}
              {consoleStatus.type === 'error' && (
                <Button
                  size="sm"
                  variant="link"
                  onClick={() => navigate('/overview')}
                >
                  返回概览
                </Button>
              )}
            </div>
            <div className="flex items-center space-x-2">
              <Button
                size="sm"
                onClick={handleManualReconnect}
                disabled={!canReconnect}
              >
                <RotateCw className="mr-1 h-3.5 w-3.5" />
                重新连接
              </Button>
              <Button variant="outline" size="sm" onClick={handleClearScreen}>
                清屏
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col flex-1 min-h-0 pt-0!">
          <ServerTerminal
            key={serverId}
            ref={terminalRef}
            onSendInput={handleSendInput}
            onReady={handleTerminalReady}
            onResize={handleTerminalResize}
            className="h-full"
          />
        </CardContent>
      </Card>
    </div>
  );
};

export default ServerConsole;
