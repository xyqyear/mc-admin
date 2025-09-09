import React from 'react';
import { Card, Progress } from 'antd';

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
    <Card title="磁盘使用空间" className={className}>
      {hasDiskUsageData && diskUsageBytes !== undefined && diskTotalBytes !== undefined && diskAvailableBytes !== undefined ? (
        <div>
          <div className="flex justify-between mb-2">
            <span className="text-base font-medium">存储空间分配</span>
            <span className="text-sm text-gray-600">
              服务器: {(diskUsageBytes / (1024 ** 3)).toFixed(1)}GB /
              剩余: {(diskAvailableBytes / (1024 ** 3)).toFixed(1)}GB /
              总计: {(diskTotalBytes / (1024 ** 3)).toFixed(1)}GB
            </span>
          </div>
          <Progress
            percent={((diskTotalBytes - diskAvailableBytes) / diskTotalBytes) * 100}
            success={{
              percent: (diskUsageBytes / diskTotalBytes) * 100,
              strokeColor: '#52c41a'
            }}
            strokeColor="#faad14"
            showInfo={false}
            size="default"
          />
          <div className="mt-2 text-xs text-gray-500">
            <span className="inline-block w-3 h-3 bg-green-500 rounded mr-1"></span>该服务器使用
            <span className="inline-block w-3 h-3 bg-yellow-500 rounded mx-1 ml-4"></span>其他文件使用
            <span className="ml-4">未填充部分为剩余空间</span>
          </div>
        </div>
      ) : (
        <div className="text-center text-gray-500 py-8">
          <p>磁盘使用信息暂不可用</p>
          <p className="text-xs">请检查服务器连接状态</p>
        </div>
      )}
    </Card>
  );
};

export default ServerDiskUsageCard;