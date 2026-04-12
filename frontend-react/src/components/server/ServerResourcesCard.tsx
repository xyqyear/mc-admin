import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { ServerInfo } from '@/types/ServerInfo';

interface ServerResourcesCardProps {
  cpuPercentage?: number;
  memoryUsageBytes?: number;
  serverInfo: ServerInfo;
  isRunning: boolean;
  hasCpuData: boolean;
  hasMemoryData: boolean;
  className?: string;
}

export const ServerResourcesCard: React.FC<ServerResourcesCardProps> = ({
  cpuPercentage,
  memoryUsageBytes,
  serverInfo,
  isRunning,
  hasCpuData,
  hasMemoryData,
  className
}) => {
  if (!isRunning || (!hasCpuData && !hasMemoryData) ||
    (cpuPercentage === undefined && memoryUsageBytes === undefined)) {
    return null;
  }

  const memoryPercent = memoryUsageBytes !== undefined
    ? (memoryUsageBytes / serverInfo.maxMemoryBytes) * 100
    : 0;

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">系统资源使用情况</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          {hasCpuData && cpuPercentage !== undefined && (
            <div>
              <div className="flex justify-between mb-1 text-sm">
                <span>CPU 使用率</span>
                <span>{cpuPercentage.toFixed(1)}%</span>
              </div>
              <Progress
                value={cpuPercentage}
                className={
                  cpuPercentage > 80 ? '**:data-[slot=progress-indicator]:bg-red-500' :
                  cpuPercentage > 60 ? '**:data-[slot=progress-indicator]:bg-yellow-500' :
                  '**:data-[slot=progress-indicator]:bg-green-500'
                }
              />
            </div>
          )}
          {hasMemoryData && memoryUsageBytes !== undefined && (
            <div>
              <div className="flex justify-between mb-1 text-sm">
                <span>内存使用</span>
                <span>
                  {(memoryUsageBytes / (1024 ** 3)).toFixed(1)}GB /
                  {(serverInfo.maxMemoryBytes / (1024 ** 3)).toFixed(1)}GB
                </span>
              </div>
              <Progress
                value={memoryPercent}
                className={
                  memoryPercent > 80 ? '**:data-[slot=progress-indicator]:bg-red-500' :
                  memoryPercent > 60 ? '**:data-[slot=progress-indicator]:bg-yellow-500' :
                  '**:data-[slot=progress-indicator]:bg-green-500'
                }
              />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default ServerResourcesCard;
