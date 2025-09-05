import React from 'react'
import { Card, Row, Col, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  DashboardOutlined,
  DatabaseOutlined,
  PlusOutlined,
  TeamOutlined,
  FileTextOutlined,
  MonitorOutlined
} from '@ant-design/icons'

const { Title, Paragraph } = Typography

const Home: React.FC = () => {
  const navigate = useNavigate()

  const featureCards = [
    {
      title: '服务器概览',
      description: '查看所有 Minecraft 服务器的运行状态和资源使用情况',
      icon: <DashboardOutlined style={{ fontSize: 32, color: '#1890ff' }} />,
      path: '/overview',
      color: '#1890ff'
    },
    {
      title: '创建服务器',
      description: '快速创建和配置新的 Minecraft 服务器实例',
      icon: <PlusOutlined style={{ fontSize: 32, color: '#52c41a' }} />,
      path: '/server/new',
      color: '#52c41a'
    },
    {
      title: '服务器管理',
      description: '管理现有服务器，查看详细信息和性能指标',
      icon: <DatabaseOutlined style={{ fontSize: 32, color: '#722ed1' }} />,
      path: '/overview',
      color: '#722ed1'
    },
    {
      title: '玩家管理',
      description: '监控在线玩家，执行管理操作和查看统计数据',
      icon: <TeamOutlined style={{ fontSize: 32, color: '#fa8c16' }} />,
      path: '/overview',
      color: '#fa8c16'
    },
    {
      title: '配置编辑',
      description: '编辑 Docker Compose 文件和服务器配置',
      icon: <FileTextOutlined style={{ fontSize: 32, color: '#eb2f96' }} />,
      path: '/overview',
      color: '#eb2f96'
    },
    {
      title: '系统监控',
      description: '实时监控系统资源使用情况和服务器性能',
      icon: <MonitorOutlined style={{ fontSize: 32, color: '#13c2c2' }} />,
      path: '/overview',
      color: '#13c2c2'
    }
  ]


  return (
    <div className="space-y-6">
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
            <Col xs={24} sm={12} lg={8} key={index}>
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
