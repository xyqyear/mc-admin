import React from 'react'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/shared/ui/dialog'
import { X, CloudUpload, Download } from 'lucide-react'

import { Card, CardHeader, CardContent, CardTitle } from '@/shared/ui/card'
import { Button } from '@/shared/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import { useTaskCenterStore } from '@/features/tasks/panelStore'
import { useActiveTasks } from '@/features/tasks/queries';
import { useDownloadTasks } from '@/features/tasks/downloadStore'
import BackgroundTaskList from '@/features/tasks/ui/BackgroundTaskList'
import DownloadTaskList from '@/features/tasks/ui/DownloadTaskList'
import { getTaskCenterPanelStyle } from '@/features/tasks/layout'

const TaskCenterPanel: React.FC = () => {
  const {
    isOpen,
    modal,
    activeTab,
    triggerPosition,
    setOpen,
    setActiveTab,
  } = useTaskCenterStore()
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

  const panel = (
    <div
      className={modal ? 'w-full' : 'fixed z-50 w-90 animate-in fade-in slide-in-from-bottom-4 duration-200'}
      style={modal ? undefined : getTaskCenterPanelStyle(
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
              aria-label="关闭任务中心"
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
  return modal ? <Dialog open={isOpen} onOpenChange={setOpen}><DialogContent showCloseButton={false} className="p-0 sm:max-w-lg"><DialogTitle className="sr-only">任务中心</DialogTitle><DialogDescription className="sr-only">查看后台任务、读取结果和取消任务</DialogDescription>{panel}</DialogContent></Dialog> : panel
}

export default TaskCenterPanel
