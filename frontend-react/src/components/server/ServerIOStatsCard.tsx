import React from 'react';
import { Card, Row, Col } from 'antd';

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
    <Card title="I/O统计" className={className}>
      <Row gutter={[16, 16]}>
        <Col span={12}>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between mb-1">
                <span>磁盘读取</span>
                <span>{(diskReadBytes / (1024 ** 2)).toFixed(1)}MB</span>
              </div>
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <span>磁盘写入</span>
                <span>{(diskWriteBytes / (1024 ** 2)).toFixed(1)}MB</span>
              </div>
            </div>
          </div>
        </Col>
        <Col span={12}>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between mb-1">
                <span>网络接收</span>
                <span>{(networkReceiveBytes / (1024 ** 2)).toFixed(1)}MB</span>
              </div>
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <span>网络发送</span>
                <span>{(networkSendBytes / (1024 ** 2)).toFixed(1)}MB</span>
              </div>
            </div>
          </div>
        </Col>
      </Row>
    </Card>
  );
};

export default ServerIOStatsCard;