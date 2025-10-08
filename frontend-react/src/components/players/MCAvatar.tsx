import React from 'react';
import { UserOutlined } from '@ant-design/icons';

interface MCAvatarProps {
  /** Base64 编码的头像图片 */
  avatarBase64?: string | null;
  /** 头像尺寸（像素） */
  size?: number;
  /** 自定义类名 */
  className?: string;
  /** 玩家名称（用于 alt 文本） */
  playerName?: string;
}

/**
 * Minecraft 玩家头像组件
 *
 * 特点：
 * - 正方形显示（不是圆形）
 * - 使用 nearest-neighbor 插值算法（image-rendering: pixelated）避免模糊
 * - 适合显示像素风格的 Minecraft 皮肤头像
 */
export const MCAvatar: React.FC<MCAvatarProps> = ({
  avatarBase64,
  size = 48,
  className = '',
  playerName = '玩家'
}) => {
  const hasAvatar = avatarBase64 && avatarBase64.trim() !== '';

  return (
    <div
      className={`inline-flex items-center justify-center flex-shrink-0 bg-gray-200 ${className}`}
      style={{
        width: size,
        height: size,
        minWidth: size,
        minHeight: size
      }}
    >
      {hasAvatar ? (
        <img
          src={`data:image/png;base64,${avatarBase64}`}
          alt={`${playerName}的头像`}
          className="w-full h-full"
          style={{
            imageRendering: 'pixelated', // 使用最近邻插值，保持像素风格
          }}
        />
      ) : (
        <UserOutlined
          style={{
            fontSize: size * 0.5,
            color: '#8c8c8c'
          }}
        />
      )}
    </div>
  );
};

export default MCAvatar;
