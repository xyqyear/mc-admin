import React, { useState, useEffect } from 'react'
import { Layout, Menu } from 'antd'
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
  SecurityScanOutlined,
} from '@ant-design/icons'
import type { MenuItem } from '@/types/MenuItem'
import { useSidebarStore } from '@/stores/useSidebarStore'

const { Sider } = Layout

type MenuItemType = Required<MenuProps>['items'][number]

// Mock server data - in real app this would come from API
const servers = [
  { id: 'vanilla' },
  { id: 'creative' },
  { id: 'fc4' },
]

const AppSidebar: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { openKeys, setOpenKeys, updateForNavigation } = useSidebarStore()

  // Update open keys when route changes (only for real navigation)
  useEffect(() => {
    updateForNavigation(location.pathname)
  }, [location.pathname, updateForNavigation])

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
            {
              title: '白名单',
              icon: <SecurityScanOutlined />,
              path: `/server/${server.id}/whitelist`,
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
      className="bg-white border-r border-gray-200"
      trigger={
        <div className="flex items-center justify-center p-2">
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </div>
      }
    >
      <Menu
        mode="inline"
        selectedKeys={[location.pathname]}
        openKeys={openKeys}
        onOpenChange={handleOpenChange}
        items={menuItems}
        className="border-r-0"
      />
    </Sider>
  )
}

export default AppSidebar
