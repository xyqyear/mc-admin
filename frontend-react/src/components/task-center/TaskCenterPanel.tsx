import React from 'react'
import { X, CloudUpload, Download } from 'lucide-react'

import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useTaskCenterStore } from '@/stores/useTaskCenterStore'
import { useTaskQueries } from '@/hooks/queries/base/useTaskQueries'
import { useDownloadTasks } from '@/stores/useDownloadStore'
import BackgroundTaskList from './BackgroundTaskList'
import DownloadTaskList from './DownloadTaskList'
import { getTaskCenterPanelStyle } from '@/config/taskCenterLayout'

const TaskCenterPanel: React.FC = () => {
  const {
    isOpen,
    activeTab,
    triggerPosition,
    setOpen,
    setActiveTab,
  } = useTaskCenterStore()
  const { useActiveTasks } = useTaskQueries()
  const { data: activeTasks } = useActiveTasks()
  const downloadTasks = useDownloadTasks()
  const [viewportSize, setViewportSize] = React.useState(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
  }))

  React.useEffect(() => {
    const handleResize = () => {
      setViewportSize({
        width: window.innerWidth,
        height: window.innerHeight,
      })
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const activeBackgroundCount = activeTasks?.length || 0
  const activeDownloadCount = downloadTasks.filter(
    (t) => t.status === 'downloading'
  ).length

  if (!isOpen) {
    return null
  }

  return (
    <div
      className="fixed z-50 w-90 animate-in fade-in slide-in-from-bottom-4 duration-200"
      style={getTaskCenterPanelStyle(
        triggerPosition,
        viewportSize.width,
        viewportSize.height
      )}
    >
      <Card className="max-h-full shadow-lg py-0 gap-0 overflow-hidden">
        <CardHeader className="py-2 px-3 border-b">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold">任务中心</CardTitle>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setOpen(false)}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Tabs
            value={activeTab}
            onValueChange={(v) => setActiveTab(v as 'background' | 'download')}
          >
            <TabsList className="w-full justify-start rounded-none border-b bg-transparent px-3 h-9">
              <TabsTrigger value="background" className="data-[state=active]:shadow-none">
                <CloudUpload className="mr-1 h-3.5 w-3.5" />
                后台任务
                {activeBackgroundCount > 0 && (
                  <span className="ml-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-blue-500 px-1 text-[10px] text-white">
                    {activeBackgroundCount}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="download" className="data-[state=active]:shadow-none">
                <Download className="mr-1 h-3.5 w-3.5" />
                下载
                {activeDownloadCount > 0 && (
                  <span className="ml-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-blue-500 px-1 text-[10px] text-white">
                    {activeDownloadCount}
                  </span>
                )}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="background" className="mt-0">
              <BackgroundTaskList />
            </TabsContent>
            <TabsContent value="download" className="mt-0">
              <DownloadTaskList />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}

export default TaskCenterPanel
