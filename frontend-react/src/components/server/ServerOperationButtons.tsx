import React from 'react';
import { Play, Square, RotateCw, ChevronDown } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { Spinner } from '@/components/ui/spinner';
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
  const { showConfirm, ConfirmDialog } = useServerOperationConfirm();

  const isOperationAvailable = (operation: string) => {
    if (!status) return false;
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
    <TooltipProvider>
      <div className="flex items-center gap-2">
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant={status === 'CREATED' || status === 'EXISTS' ? 'default' : 'outline'}
                disabled={!isOperationAvailable('start') && !isOperationAvailable('up')}
                onClick={handleStartServer}
              >
                {serverOperationMutation.isPending
                  ? <Spinner className="mr-2 size-4" />
                  : <Play className="mr-2 h-4 w-4" />
                }
                启动
              </Button>
            }
          />
          <TooltipContent>启动服务器</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="destructive"
                disabled={!isOperationAvailable('stop')}
                onClick={() => handleConfirmableServerOperation('stop')}
              >
                {serverOperationMutation.isPending
                  ? <Spinner className="mr-2 size-4" />
                  : <Square className="mr-2 h-4 w-4" />
                }
                停止
              </Button>
            }
          />
          <TooltipContent>停止服务器</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="destructive"
                disabled={!isOperationAvailable('restart')}
                onClick={() => handleConfirmableServerOperation('restart')}
              >
                {serverOperationMutation.isPending
                  ? <Spinner className="mr-2 size-4" />
                  : <RotateCw className="mr-2 h-4 w-4" />
                }
                重启
              </Button>
            }
          />
          <TooltipContent>重启服务器</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="destructive"
                disabled={!isOperationAvailable('down')}
                onClick={() => handleConfirmableServerOperation('down')}
              >
                {serverOperationMutation.isPending
                  ? <Spinner className="mr-2 size-4" />
                  : <ChevronDown className="mr-2 h-4 w-4" />
                }
                下线
              </Button>
            }
          />
          <TooltipContent>下线服务器</TooltipContent>
        </Tooltip>
        {showReturnButton && (
          <Button variant="outline" onClick={() => navigate('/overview')}>返回总览</Button>
        )}
      </div>
      <ConfirmDialog />
    </TooltipProvider>
  );
};

export default ServerOperationButtons;
