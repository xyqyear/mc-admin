import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

interface ServerDiskUsageCardProps {
  diskUsageBytes?: number;
  diskTotalBytes?: number;
  diskAvailableBytes?: number;
  hasDiskUsageData: boolean;
  className?: string;
}

export const ServerDiskUsageCard: React.FC<ServerDiskUsageCardProps> = ({
  diskUsageBytes,
  diskTotalBytes,
  diskAvailableBytes,
  hasDiskUsageData,
  className
}) => {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">磁盘使用空间</CardTitle>
      </CardHeader>
      <CardContent>
        {hasDiskUsageData && diskUsageBytes !== undefined && diskTotalBytes !== undefined && diskAvailableBytes !== undefined ? (
          <div>
            <div className="flex justify-between mb-2">
              <span className="text-sm font-medium">存储空间分配</span>
              <span className="text-xs text-muted-foreground">
                服务器: {(diskUsageBytes / (1024 ** 3)).toFixed(1)}GB /
                剩余: {(diskAvailableBytes / (1024 ** 3)).toFixed(1)}GB /
                总计: {(diskTotalBytes / (1024 ** 3)).toFixed(1)}GB
              </span>
            </div>
            <div className="h-2 w-full rounded-full bg-muted overflow-hidden flex">
              <div
                className="h-full bg-green-500 transition-all"
                style={{ width: `${(diskUsageBytes / diskTotalBytes) * 100}%` }}
              />
              <div
                className="h-full bg-yellow-500 transition-all"
                style={{ width: `${((diskTotalBytes - diskAvailableBytes - diskUsageBytes) / diskTotalBytes) * 100}%` }}
              />
            </div>
            <div className="mt-2 text-xs text-muted-foreground flex items-center gap-4">
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 bg-green-500 rounded" />
                该服务器使用
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 bg-yellow-500 rounded" />
                其他文件使用
              </span>
              <span>未填充部分为剩余空间</span>
            </div>
          </div>
        ) : (
          <div className="text-center text-muted-foreground py-8">
            <p>磁盘使用信息暂不可用</p>
            <p className="text-xs mt-1">请检查服务器连接状态</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default ServerDiskUsageCard;
