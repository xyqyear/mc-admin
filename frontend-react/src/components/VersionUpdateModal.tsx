import React from 'react'
import { Modal, Button, Typography, Timeline, Tag, Space, Divider } from 'antd'
import { ClockCircleOutlined, CheckCircleOutlined, BugOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { compareVersions, versionUpdates } from '@/config/versionConfig'

const { Title, Text, Paragraph } = Typography

interface VersionUpdateModalProps {
  visible: boolean
  onClose: () => void
  onRemindLater: () => void
  fromVersion: string
  toVersion: string
}

const VersionUpdateModal: React.FC<VersionUpdateModalProps> = ({
  visible,
  onClose,
  onRemindLater,
  fromVersion,
  toVersion
}) => {
  const relevantUpdates = versionUpdates
    .filter(update =>
      compareVersions(update.version, fromVersion) > 0 &&
      compareVersions(update.version, toVersion) <= 0
    )
    .sort((a, b) => compareVersions(b.version, a.version))

  const renderUpdateItem = (type: 'features' | 'fixes' | 'improvements', items: string[] = []) => {
    if (items.length === 0) return null

    const config = {
      features: { icon: <ThunderboltOutlined />, color: 'blue', title: '新功能' },
      fixes: { icon: <BugOutlined />, color: 'red', title: '问题修复' },
      improvements: { icon: <CheckCircleOutlined />, color: 'green', title: '优化改进' }
    }

    const { icon, color, title } = config[type]

    return (
      <div className="mb-4">
        <Space>
          {icon}
          <Text strong style={{ color }}>{title}：</Text>
        </Space>
        <ul className="ml-6 mt-2">
          {items.map((item, index) => (
            <li key={index} className="mb-1">
              <Text>{item}</Text>
            </li>
          ))}
        </ul>
      </div>
    )
  }

  return (
    <Modal
      title={
        <Space>
          <ThunderboltOutlined className="text-blue-500" />
          <span>版本更新通知</span>
        </Space>
      }
      open={visible}
      onCancel={onRemindLater}
      width={720}
      footer={[
        <Button key="later" onClick={onRemindLater}>
          稍后提醒我
        </Button>,
        <Button key="close" type="primary" onClick={onClose}>
          明白了
        </Button>
      ]}
    >
      <div className="py-4">
        <div className="mb-6 text-center">
          <Title level={4} className="mb-2">
            欢迎使用 MC Admin v{toVersion}！
          </Title>
          <Text type="secondary">
            从 v{fromVersion} 到 v{toVersion} 的更新内容
          </Text>
        </div>

        <Divider />

        {relevantUpdates.length > 0 ? (
          <Timeline
            items={relevantUpdates.map(update => ({
              dot: <ClockCircleOutlined className="text-blue-500" />,
              children: (
                <div>
                  <div className="mb-3">
                    <Space>
                      <Tag color="blue" className="font-medium">
                        v{update.version}
                      </Tag>
                      <Text type="secondary" className="text-sm">
                        {update.date}
                      </Text>
                    </Space>
                    <Title level={5} className="mt-2 mb-2">
                      {update.title}
                    </Title>
                    <Paragraph className="text-gray-600">
                      {update.description}
                    </Paragraph>
                  </div>

                  <div className="ml-4">
                    {renderUpdateItem('features', update.features)}
                    {renderUpdateItem('improvements', update.improvements)}
                    {renderUpdateItem('fixes', update.fixes)}
                  </div>
                </div>
              )
            }))}
          />
        ) : (
          <div className="text-center py-8">
            <Text type="secondary">暂无更新记录</Text>
          </div>
        )}
      </div>
    </Modal>
  )
}

export default VersionUpdateModal;