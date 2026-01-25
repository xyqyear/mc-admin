import React from 'react';
import { Tag, Tooltip } from 'antd';
import { useNavigate } from 'react-router-dom';

interface ServerNameTagProps {
  serverId: string;
  maxLength?: number;
  color?: string;
}

/**
 * 显示服务器名称的Tag组件
 * - 支持最大长度限制，超过时截断并显示省略号
 * - 鼠标悬浮显示完整服务器名
 * - 点击跳转到服务器总览页面
 */
export const ServerNameTag: React.FC<ServerNameTagProps> = ({
  serverId,
  maxLength,
  color = 'blue'
}) => {
  const navigate = useNavigate();

  const needsTruncate = maxLength && serverId.length > maxLength;
  const displayText = needsTruncate
    ? `${serverId.slice(0, maxLength)}...`
    : serverId;

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigate(`/server/${serverId}`);
  };

  return (
    <Tooltip title={serverId}>
      <Tag
        color={color}
        style={{ cursor: 'pointer' }}
        onClick={handleClick}
      >
        {displayText}
      </Tag>
    </Tooltip>
  );
};

export default ServerNameTag;
