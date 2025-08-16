import React from 'react'
import { Layout, Button } from 'antd'
import { LogoutOutlined } from '@ant-design/icons'
import { useTokenStore } from '@/stores/useTokenStore'
import { useNavigate } from 'react-router-dom'

const { Header } = Layout

const AppHeader: React.FC = () => {
  const { clearToken } = useTokenStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    clearToken()
    navigate('/login')
  }

  return (
    <Header className="bg-white border-b border-gray-200 flex items-center justify-between px-4">
      <div className="flex-1" />
      <Button
        icon={<LogoutOutlined />}
        onClick={handleLogout}
        type="text"
        className="flex items-center"
      >
        退出登录
      </Button>
    </Header>
  )
}

export default AppHeader
