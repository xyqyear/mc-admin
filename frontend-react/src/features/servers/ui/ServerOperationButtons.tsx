import React from 'react';
import { openTaskCenter } from '@/features/tasks/commands';
import { Play, Square, RotateCw, ChevronDown } from 'lucide-react';
import { useNavigate } from 'react-router';

import { Button } from '@/shared/ui/button';
import { Spinner } from '@/shared/ui/spinner';
import { useServerOperation } from '@/features/servers/commands';
import { useServerOperationConfirm } from '@/features/servers/ui/ServerOperationConfirmDialog';
import { serverStatusUtils } from '@/features/servers/presentation';
import type { ServerStatus } from '@/features/servers/contracts';
import { useServerMaintenance } from '@/features/servers/queries';

interface ServerOperationButtonsProps {
  serverId: string;
  serverName: string;
  status?: ServerStatus;
  showReturnButton?: boolean;
  maintenanceActive?: boolean;
}

const ServerOperationButtons: React.FC<ServerOperationButtonsProps> = ({
  serverId,
  serverName,
  status,
  showReturnButton = true,
  maintenanceActive = false
}) => {
  const navigate = useNavigate();
  const serverOperationMutation = useServerOperation();
  const { showConfirm, confirmDialog } = useServerOperationConfirm();
  const maintenance = useServerMaintenance(serverId);

  const isPending = serverOperationMutation.isPending || Boolean(maintenance.data?.task_id);
  const taskId = maintenance.data?.task_id ?? (serverOperationMutation.isPending ? serverOperationMutation.taskId : null);
  const reason = maintenance.data?.active ? maintenance.data.description : serverOperationMutation.isPending ? '正在提交并等待操作完成' : null;

  const isOperationAvailable = (operation: string) => {
    if (!status) return false;
    if ((maintenanceActive || maintenance.data?.active) && ['start', 'up', 'restart'].includes(operation)) return false;
    return serverStatusUtils.isOperationAvailable(operation, status);
  };

  const handleStartServer = () => {
    if (!status) return;
    const operation = status === 'CREATED' ? 'start' : 'up';
    serverOperationMutation.mutate({ action: operation, serverId });
  };

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
    <>
      <Button
        variant={status === 'CREATED' || status === 'EXISTS' ? 'default' : 'outline'}
        disabled={isPending || (!isOperationAvailable('start') && !isOperationAvailable('up'))}
        onClick={handleStartServer}
        title={maintenance.data?.active ? maintenance.data.description ?? '服务器正在维护' : '启动服务器'}
      >
        {isPending
          ? <Spinner aria-hidden="true" className="mr-2 size-4" />
          : <Play className="mr-2 h-4 w-4" />
        }
        启动
      </Button>
      <Button
        variant="destructive"
        disabled={isPending || !isOperationAvailable('stop')}
        onClick={() => handleConfirmableServerOperation('stop')}
        title="停止服务器"
      >
        {isPending
          ? <Spinner aria-hidden="true" className="mr-2 size-4" />
          : <Square className="mr-2 h-4 w-4" />
        }
        停止
      </Button>
      <Button
        variant="destructive"
        disabled={isPending || !isOperationAvailable('restart')}
        onClick={() => handleConfirmableServerOperation('restart')}
        title="重启服务器"
      >
        {isPending
          ? <Spinner aria-hidden="true" className="mr-2 size-4" />
          : <RotateCw className="mr-2 h-4 w-4" />
        }
        重启
      </Button>
      <Button
        variant="destructive"
        disabled={isPending || !isOperationAvailable('down')}
        onClick={() => handleConfirmableServerOperation('down')}
        title="下线服务器"
      >
        {isPending
          ? <Spinner aria-hidden="true" className="mr-2 size-4" />
          : <ChevronDown className="mr-2 h-4 w-4" />
        }
        下线
      </Button>
      {showReturnButton && (
        <Button variant="outline" onClick={() => navigate('/overview')}>返回总览</Button>
      )}
      {reason && (
        <div role="status" className="flex basis-full items-center gap-2 text-sm text-muted-foreground">
          <span>{reason}</span>
          {taskId && <Button variant="link" size="sm" onClick={openTaskCenter}>查看任务</Button>}
        </div>
      )}
      {confirmDialog}
    </>
  );
};

export default ServerOperationButtons;
