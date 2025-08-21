import React from 'react'
import { Layout } from 'antd'
import AppHeader from './AppHeader'
import AppSidebar from './AppSidebar'

const { Content } = Layout

interface MainLayoutProps {
  children: React.ReactNode
}

export const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  return (
    <Layout className="h-screen">
      <AppHeader />
      <Layout>
        <AppSidebar />
        <Layout>
          <Content className="p-4 overflow-auto">
            {children}
          </Content>
        </Layout>
      </Layout>
    </Layout>
  )
}

export default MainLayout
