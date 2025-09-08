import React from 'react';
import { Button, Tooltip, Space } from 'antd';
import {
  PlayCircleOutlined,
  StopOutlined,
  ReloadOutlined,
  DownOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

import { useServerMutations } from '@/hooks/mutations/useServerMutations';
import { useServerOperationConfirm } from '@/components/modals/ServerOperationConfirmModal';
import { serverStatusUtils } from '@/utils/serverUtils';
import { ServerStatus } from '@/types/ServerInfo';

interface ServerOperationButtonsProps {
  serverId: string;
  serverName: string;
  status?: ServerStatus;
  showReturnButton?: boolean;
}

const ServerOperationButtons: React.FC<ServerOperationButtonsProps> = ({
  serverId,
  serverName,
  status,
  showReturnButton = true
}) => {
  const navigate = useNavigate();
  const { useServerOperation } = useServerMutations();
  const serverOperationMutation = useServerOperation();
  const { showConfirm } = useServerOperationConfirm();

  // 检查操作是否可用
  const isOperationAvailable = (operation: string) => {
    if (!status) return false;
    return serverStatusUtils.isOperationAvailable(operation, status);
  };

  // 智能启动：根据服务器状态决定使用 start 还是 up
  const handleStartServer = () => {
    if (!status) return;

    // 根据状态决定操作类型
    const operation = status === 'CREATED' ? 'start' : 'up';

    serverOperationMutation.mutate({ action: operation, serverId });
  };

  // 需要确认的服务器操作处理（停止、重启、下线）
  const handleConfirmableServerOperation = (operation: 'stop' | 'restart' | 'down') => {
    showConfirm({
      operation,
      serverName,
      serverId,
      onConfirm: (action, serverId) => {
        serverOperationMutation.mutate({ action, serverId });
      }
    });
  };

  return (
    <Space>
      <Tooltip title="启动服务器">
        <Button
          type={status === 'CREATED' || status === 'EXISTS' ? 'primary' : 'default'}
          icon={<PlayCircleOutlined />}
          disabled={!isOperationAvailable('start') && !isOperationAvailable('up')}
          loading={serverOperationMutation.isPending}
          onClick={handleStartServer}
        >
          启动
        </Button>
      </Tooltip>
      <Tooltip title="停止服务器">
        <Button
          danger
          icon={<StopOutlined />}
          disabled={!isOperationAvailable('stop')}
          loading={serverOperationMutation.isPending}
          onClick={() => handleConfirmableServerOperation('stop')}
        >
          停止
        </Button>
      </Tooltip>
      <Tooltip title="重启服务器">
        <Button
          danger
          icon={<ReloadOutlined />}
          disabled={!isOperationAvailable('restart')}
          loading={serverOperationMutation.isPending}
          onClick={() => handleConfirmableServerOperation('restart')}
        >
          重启
        </Button>
      </Tooltip>
      <Tooltip title="下线服务器">
        <Button
          danger
          icon={<DownOutlined />}
          disabled={!isOperationAvailable('down')}
          loading={serverOperationMutation.isPending}
          onClick={() => handleConfirmableServerOperation('down')}
        >
          下线
        </Button>
      </Tooltip>
      {showReturnButton && (
        <Button onClick={() => navigate('/overview')}>返回总览</Button>
      )}
    </Space>
  );
};

export default ServerOperationButtons;