import React from 'react'
import { Card, Row, Col, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  DatabaseOutlined,
  PlusOutlined,
  TeamOutlined,
  CloudDownloadOutlined,
  FileZipOutlined,
  GlobalOutlined,
  ClockCircleOutlined,
  SettingOutlined
} from '@ant-design/icons'

const { Title, Paragraph } = Typography

const Home: React.FC = () => {
  const navigate = useNavigate()

  const featureCards = [
    {
      title: '服务器管理',
      description: '管理现有服务器，查看详细信息和性能指标',
      icon: <DatabaseOutlined style={{ fontSize: 32, color: '#722ed1' }} />,
      path: '/overview',
      color: '#722ed1'
    },
    {
      title: '创建服务器',
      description: '快速创建和配置新的 Minecraft 服务器实例',
      icon: <PlusOutlined style={{ fontSize: 32, color: '#52c41a' }} />,
      path: '/server/new',
      color: '#52c41a'
    },
    {
      title: '玩家管理',
      description: '查看玩家信息、在线状态和游戏记录',
      icon: <TeamOutlined style={{ fontSize: 32, color: '#13c2c2' }} />,
      path: '/players',
      color: '#13c2c2'
    },
    {
      title: '快照管理',
      description: '创建和管理服务器快照，支持数据备份和恢复操作',
      icon: <CloudDownloadOutlined style={{ fontSize: 32, color: '#fa8c16' }} />,
      path: '/snapshots',
      color: '#fa8c16'
    },
    {
      title: '归档管理',
      description: '管理服务器归档文件，支持上传和删除服务器压缩包',
      icon: <FileZipOutlined style={{ fontSize: 32, color: '#eb2f96' }} />,
      path: '/archives',
      color: '#eb2f96'
    },
    {
      title: 'DNS管理',
      description: '管理域名解析记录，配置服务器地址映射',
      icon: <GlobalOutlined style={{ fontSize: 32, color: '#2f54eb' }} />,
      path: '/dns',
      color: '#2f54eb'
    },
    {
      title: '任务管理',
      description: '配置定时任务，自动执行备份和重启等操作',
      icon: <ClockCircleOutlined style={{ fontSize: 32, color: '#faad14' }} />,
      path: '/cron',
      color: '#faad14'
    },
    {
      title: '动态配置',
      description: '管理系统配置参数，自定义平台行为',
      icon: <SettingOutlined style={{ fontSize: 32, color: '#595959' }} />,
      path: '/config',
      color: '#595959'
    }
  ]


  return (
    <div className="space-y-4">
      {/* Header Section */}
      <div className="text-center space-y-4">
        <Title level={1} className="!mb-0">
          MC Admin 管理系统
        </Title>
        <Paragraph className="text-lg text-gray-600 max-w-2xl mx-auto">
          专业的 Minecraft 服务器管理平台，提供完整的服务器生命周期管理和监控功能
        </Paragraph>
      </div>

      {/* Feature Cards Grid */}
      <div>
        <Title level={2} className="text-center !mb-8">核心功能</Title>
        <Row gutter={[24, 24]}>
          {featureCards.map((card, index) => (
            <Col xs={24} sm={12} lg={6} key={index}>
              <Card
                hoverable
                className="h-full transition-all duration-300 hover:shadow-lg"
                styles={{ body: { padding: '32px 24px' } }}
                onClick={() => navigate(card.path)}
              >
                <div className="text-center space-y-4">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-100">
                    {React.cloneElement(card.icon, {
                      style: { fontSize: 28, color: card.color }
                    })}
                  </div>
                  <Title level={4} className="!mb-2">{card.title}</Title>
                  <Paragraph className="text-gray-600 text-sm leading-relaxed">
                    {card.description}
                  </Paragraph>
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      </div>
    </div>
  )
}

export default Home
