import React, { useEffect, useRef, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Switch, Button, Space, Alert, Typography, Spin } from 'antd';
import { ReloadOutlined, DisconnectOutlined, LinkOutlined, CodeOutlined } from '@ant-design/icons';

import { useServerQueries } from '@/hooks/queries/base/useServerQueries';
import { useServerConsoleWebSocket } from '@/hooks/useServerConsoleWebSocket';
import PageHeader from '@/components/layout/PageHeader';
import LoadingSpinner from '@/components/layout/LoadingSpinner';
import ServerOperationButtons from '@/components/server/ServerOperationButtons';
import ServerStateTag from '@/components/overview/ServerStateTag';
import ServerTerminal, { ServerTerminalRef } from '@/components/server/ServerTerminal';
import { ServerInfo, ServerStatus } from '@/types/ServerInfo';

const { Text } = Typography;

interface ServerConsoleInnerProps {
  serverId: string;
  serverInfo: ServerInfo;
  serverStatus?: ServerStatus;
}

const ServerConsoleInner: React.FC<ServerConsoleInnerProps> = ({
  serverId,
  serverInfo,
  serverStatus
}) => {
  // 终端引用
  const terminalRef = useRef<ServerTerminalRef>(null);

  // 检查服务器状态是否允许WebSocket连接
  const canConnectWebSocket = useMemo(() => {
    if (!serverStatus) return false;
    return serverStatus !== 'REMOVED' && serverStatus !== 'EXISTS';
  }, [serverStatus]);

  // WebSocket hook
  const {
    connectionState,
    lastError,
    filterRcon,
    sendCommand,
    setFilterRcon,
    onMessage,
    connect,
    disconnect
  } = useServerConsoleWebSocket(serverId, canConnectWebSocket);

  // 终端准备就绪时设置消息监听器
  const handleTerminalReady = useCallback((terminal: ServerTerminalRef) => {
    // 注册消息监听器，将WebSocket消息传递给终端
    onMessage((message) => {
      if (terminal.onMessage) {
        terminal.onMessage(message);
      }
    });
  }, [onMessage]);

  // 处理终端命令
  const handleCommand = useCallback((command: string) => {
    sendCommand(command);
  }, [sendCommand]);

  // 处理过滤开关变化
  const handleFilterChange = useCallback((checked: boolean) => {
    setFilterRcon(checked);
  }, [setFilterRcon]);

  // 手动重连
  const handleManualReconnect = useCallback(() => {
    disconnect();
    setTimeout(() => {
      connect();
    }, 100);
  }, [disconnect, connect]);

  // 清屏
  const handleClearScreen = useCallback(() => {
    if (terminalRef.current) {
      terminalRef.current.clear();
    }
  }, []);

  // 连接成功时显示连接信息
  useEffect(() => {
    if (connectionState === 'CONNECTED' && terminalRef.current) {
      terminalRef.current.clear();
      terminalRef.current.write('\x1b[32mConnected to server console\x1b[0m\r\n');
    } else if (connectionState === 'DISCONNECTED' && terminalRef.current) {
      terminalRef.current.write('\x1b[33mDisconnected from server console\x1b[0m\r\n');
    } else if (connectionState === 'ERROR' && terminalRef.current) {
      terminalRef.current.write('\x1b[31mConnection error\x1b[0m\r\n');
    } else if (connectionState === 'RETRYING' && terminalRef.current) {
      terminalRef.current.write('\x1b[33mRetrying connection...\x1b[0m\r\n');
    }
  }, [connectionState]);

  // 获取连接状态显示
  const getConnectionStatus = () => {
    switch (connectionState) {
      case 'CONNECTED':
        return { text: '已连接', color: 'success', icon: <LinkOutlined /> };
      case 'CONNECTING':
        return { text: '正在连接...', color: 'processing', icon: <Spin size="small" /> };
      case 'RETRYING':
        return { text: '正在重试...', color: 'warning', icon: <Spin size="small" /> };
      case 'ERROR':
        return { text: '连接错误', color: 'error', icon: <DisconnectOutlined /> };
      default:
        return { text: '已断开连接', color: 'default', icon: <DisconnectOutlined /> };
    }
  };

  const connectionStatus = getConnectionStatus();

  return (
    <div className="h-full flex flex-col space-y-4">
      <PageHeader
        title="控制台"
        icon={<CodeOutlined />}
        serverTag={serverInfo?.name}
        actions={
          <ServerOperationButtons
            serverId={serverId}
            serverName={serverInfo?.name}
            status={serverStatus}
          />
        }
      />

      {lastError && (
        <Alert
          message="连接错误"
          description={lastError}
          type="error"
          showIcon
          closable
          onClose={() => {
            // 可以在这里调用清除错误的函数，但目前WebSocket hook没有提供
          }}
        />
      )}

      {serverStatus && !canConnectWebSocket && (
        <Alert
          message="控制台不可用"
          description={
            <span>
              控制台仅在服务器状态不是 <ServerStateTag state="REMOVED" /> 或 <ServerStateTag state="EXISTS" /> 时可用。当前状态: <ServerStateTag state={serverStatus} />
            </span>
          }
          type="info"
          showIcon
        />
      )}

      {/* 控制台容器 */}
      <Card
        className="flex-1 min-h-0 flex flex-col"
        classNames={{ body: "flex flex-col flex-1 !p-4" }}
        title={
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <Text type="secondary">连接状态:</Text>
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
            </div>
            <div className="flex items-center space-x-2">
              <Button
                icon={<ReloadOutlined />}
                onClick={handleManualReconnect}
                disabled={connectionState === 'CONNECTING'}
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
        {/* 终端区域 */}
        <ServerTerminal
          ref={terminalRef}
          onCommand={handleCommand}
          onReady={handleTerminalReady}
          className="h-full"
        />
      </Card>
    </div>
  );
};

const ServerConsole: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const serverId = id!;

  // React Query hooks for data loading and error checking
  const { useServerStatus, useServerInfo } = useServerQueries();
  const { data: serverStatus } = useServerStatus(serverId);
  const { data: serverInfo, isLoading: serverInfoLoading, isError: serverInfoError } = useServerInfo(serverId);

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
    );
  }

  // 错误状态
  if (serverInfoError) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert
          message="加载失败"
          description={`无法加载服务器 "${serverId}" 的信息`}
          type="error"
          action={
            <Button size="small" onClick={() => navigate('/overview')}>
              返回概览
            </Button>
          }
        />
      </div>
    );
  }

  // 加载状态
  if (serverInfoLoading || !serverInfo) {
    return <LoadingSpinner height="16rem" tip="加载服务器信息中..." />;
  }

  // 所有数据就绪，渲染内层组件
  return (
    <ServerConsoleInner
      key={serverId}
      serverId={serverId}
      serverInfo={serverInfo}
      serverStatus={serverStatus}
    />
  );
};

export default ServerConsole;