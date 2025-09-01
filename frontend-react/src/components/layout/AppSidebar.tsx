import React, { useState, useEffect } from 'react'
import { Layout, Menu, Button } from 'antd'
import { useNavigate, useLocation } from 'react-router-dom'
import type { MenuProps } from 'antd'
import {
  HomeOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  PlusOutlined,
  SaveOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  DesktopOutlined,
  UserOutlined,
  SettingOutlined,
  FolderOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import type { MenuItem } from '@/types/MenuItem'
import { useSidebarStore } from '@/stores/useSidebarStore'
import { useServerQueries } from '@/hooks/queries/useServerQueries'
import { useTokenStore } from '@/stores/useTokenStore'

const { Sider } = Layout

type MenuItemType = Required<MenuProps>['items'][number]

const AppSidebar: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { openKeys, setOpenKeys, updateForNavigation } = useSidebarStore()
  const { clearToken } = useTokenStore()
  
  // 获取服务器列表数据
  const { useServers } = useServerQueries()
  const serversQuery = useServers()
  const servers = serversQuery.data || []

  // Update open keys when route changes (only for real navigation)
  useEffect(() => {
    updateForNavigation(location.pathname)
  }, [location.pathname, updateForNavigation])

  const handleLogout = () => {
    clearToken()
    navigate('/login')
  }

  const menuItemsData: MenuItem[] = [
    {
      title: '首页',
      icon: <HomeOutlined />,
      path: '/',
    },
    {
      title: '服务器总览',
      icon: <DashboardOutlined />,
      path: '/overview',
    },
    {
      title: '服务器管理',
      icon: <DatabaseOutlined />,
      items: [
        ...servers.map(server => ({
          title: server.id,
          icon: <DesktopOutlined />,
          items: [
            {
              title: '概览',
              icon: <DashboardOutlined />,
              path: `/server/${server.id}`,
            },
            {
              title: '玩家列表',
              icon: <UserOutlined />,
              path: `/server/${server.id}/players`,
            },
            {
              title: '设置',
              icon: <SettingOutlined />,
              path: `/server/${server.id}/compose`,
            },
            {
              title: '文件',
              icon: <FolderOutlined />,
              path: `/server/${server.id}/files`,
            },
          ],
        })),
        {
          title: '新建',
          icon: <PlusOutlined />,
          path: '/server/new',
        },
      ],
    },
    {
      title: '备份管理',
      icon: <SaveOutlined />,
      path: '/backups',
    },
  ]

  const handleMenuClick = (path: string) => {
    navigate(path)
  }

  const handleOpenChange = (keys: string[]) => {
    setOpenKeys(keys)
  }

  const convertToMenuItems = (items: MenuItem[]): MenuItemType[] => {
    return items.map((item) => {
      if (item.items) {
        return {
          key: item.path || item.title,
          icon: item.icon,
          label: item.title,
          children: convertToMenuItems(item.items),
        }
      }
      
      return {
        key: item.path!,
        icon: item.icon,
        label: item.title,
        onClick: () => item.path && handleMenuClick(item.path),
      }
    })
  }

  const menuItems = convertToMenuItems(menuItemsData)

  return (
    <Sider
      collapsible
      collapsed={collapsed}
      onCollapse={setCollapsed}
      className="bg-white border-r border-gray-200 [&_.ant-layout-sider-trigger]:flex [&_.ant-layout-sider-trigger]:items-center [&_.ant-layout-sider-trigger]:justify-center [&_.ant-layout-sider-trigger]:p-0"
      trigger={
        <div className="flex items-center justify-center w-full h-full text-center">
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </div>
      }
    >
      <div className="flex flex-col h-full">
        {/* 退出登录按钮 */}
        <div className="p-3 border-b border-gray-200">
          <Button
            icon={<LogoutOutlined />}
            onClick={handleLogout}
            type="text"
            block
            className="flex items-center justify-center"
          >
            {!collapsed && "退出登录"}
          </Button>
        </div>
        
        {/* 菜单 */}
        <div className="flex-1">
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            openKeys={openKeys}
            onOpenChange={handleOpenChange}
            items={menuItems}
            className="border-r-0"
          />
        </div>
      </div>
    </Sider>
  )
}

export default AppSidebar
