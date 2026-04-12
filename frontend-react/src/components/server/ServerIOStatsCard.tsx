import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

interface ServerIOStatsCardProps {
  diskReadBytes?: number;
  diskWriteBytes?: number;
  networkReceiveBytes?: number;
  networkSendBytes?: number;
  isRunning: boolean;
  hasIOStatsData: boolean;
  className?: string;
}

export const ServerIOStatsCard: React.FC<ServerIOStatsCardProps> = ({
  diskReadBytes,
  diskWriteBytes,
  networkReceiveBytes,
  networkSendBytes,
  isRunning,
  hasIOStatsData,
  className
}) => {
  if (!isRunning || !hasIOStatsData ||
    diskReadBytes === undefined || diskWriteBytes === undefined ||
    networkReceiveBytes === undefined || networkSendBytes === undefined) {
    return null;
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">I/O统计</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-4">
            <div className="flex justify-between text-sm">
              <span>磁盘读取</span>
              <span>{(diskReadBytes / (1024 ** 2)).toFixed(1)}MB</span>
            </div>
            <div className="flex justify-between text-sm">
              <span>磁盘写入</span>
              <span>{(diskWriteBytes / (1024 ** 2)).toFixed(1)}MB</span>
            </div>
          </div>
          <div className="space-y-4">
            <div className="flex justify-between text-sm">
              <span>网络接收</span>
              <span>{(networkReceiveBytes / (1024 ** 2)).toFixed(1)}MB</span>
            </div>
            <div className="flex justify-between text-sm">
              <span>网络发送</span>
              <span>{(networkSendBytes / (1024 ** 2)).toFixed(1)}MB</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default ServerIOStatsCard;
