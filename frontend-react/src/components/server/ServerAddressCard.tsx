import React from 'react';
import { Card, Typography, Button, Space, message, Tag } from 'antd';
import { CopyOutlined, LinkOutlined } from '@ant-design/icons';
import { generateServerAddresses } from '@/config/serverAddressConfig';

const { Title, Text } = Typography;

interface ServerAddressCardProps {
  serverId: string;
  className?: string;
}

export const ServerAddressCard: React.FC<ServerAddressCardProps> = ({ serverId, className }) => {
  const addresses = generateServerAddresses(serverId);

  const handleCopyAddress = async (address: string) => {
    try {
      await navigator.clipboard.writeText(address);
      message.success(`Address copied: ${address}`);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = address;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      message.success(`Address copied: ${address}`);
    }
  };

  return (
    <Card
      className={className}
      title={
        <Space align="center">
          <LinkOutlined />
          <Title level={5} style={{ margin: 0 }}>
            服务器地址
          </Title>
        </Space>
      }
    >
      <div className="space-y-3">
        {addresses.map(({ address, label }) => {
          return (
            <div key={address} className="flex items-center space-x-3">
              <Button
                type="text"
                size="small"
                icon={<CopyOutlined />}
                onClick={() => handleCopyAddress(address)}
                className="flex-shrink-0"
                title={`Copy ${address}`}
              />
              <div className="flex items-center space-x-2 flex-1">
                <Text
                  code
                  className="text-sm font-mono"
                  style={{ fontSize: '13px' }}
                >
                  {address}
                </Text>
                <Tag color="blue" className="text-center">
                  {label}
                </Tag>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

export default ServerAddressCard;