import React from 'react'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import AppSidebar from '@/components/layout/AppSidebar'
import { TaskCenterPanel, TaskCenterTrigger } from '@/components/task-center'

interface MainLayoutProps {
  children: React.ReactNode
}

export const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  return (
    <SidebarProvider className="h-screen">
      <AppSidebar />
      <SidebarInset className="overflow-hidden">
        <main className="flex-1 p-4 overflow-auto">{children}</main>
      </SidebarInset>
      <TaskCenterPanel />
      <TaskCenterTrigger />
    </SidebarProvider>
  )
}

export default MainLayout
