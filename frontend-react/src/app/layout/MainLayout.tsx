import React from 'react'
import { SidebarInset, SidebarProvider } from '@/shared/ui/sidebar'
import AppSidebar from '@/app/layout/AppSidebar'
import { TaskCenterPanel, TaskCenterTrigger } from '@/features/tasks/ui/index'
import SelfCheckGlobalIndicator from '@/features/health/ui/SelfCheckGlobalIndicator'

interface MainLayoutProps {
  children: React.ReactNode
}

export const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  return (
    <SidebarProvider
      className="h-screen"
      style={{ '--sidebar-width': '14rem' } as React.CSSProperties}
    >
      <AppSidebar />
      <SidebarInset className="overflow-hidden">
        <SelfCheckGlobalIndicator />
        <main className="flex-1 p-4 overflow-auto">{children}</main>
      </SidebarInset>
      <TaskCenterPanel />
      <TaskCenterTrigger />
    </SidebarProvider>
  )
}

export default MainLayout
