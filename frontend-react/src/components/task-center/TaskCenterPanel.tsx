import React from 'react'
import { Card, Tabs, Typography } from 'antd'
import {
  CloseOutlined,
  CloudSyncOutlined,
  DownloadOutlined,
} from '@ant-design/icons'
import { useTaskCenterStore } from '@/stores/useTaskCenterStore'
import { useTaskQueries } from '@/hooks/queries/base/useTaskQueries'
import { useDownloadTasks } from '@/stores/useDownloadStore'
import BackgroundTaskList from './BackgroundTaskList'
import DownloadTaskList from './DownloadTaskList'

const { Text } = Typography

const TaskCenterPanel: React.FC = () => {
  const { isOpen, activeTab, setOpen, setActiveTab } = useTaskCenterStore()
  const { useActiveTasks } = useTaskQueries()
  const { data: activeTasks } = useActiveTasks()
  const downloadTasks = useDownloadTasks()

  // Count active tasks
  const activeBackgroundCount = activeTasks?.length || 0
  const activeDownloadCount = downloadTasks.filter(
    (t) => t.status === 'downloading'
  ).length

  if (!isOpen) {
    return null
  }

  const tabItems = [
    {
      key: 'background',
      label: (
        <span className="flex items-center gap-1.5">
          <CloudSyncOutlined />
          后台任务
          {activeBackgroundCount > 0 && (
            <span className="bg-blue-500 text-white text-xs px-1.5 py-0.5 rounded-full min-w-5 text-center">
              {activeBackgroundCount}
            </span>
          )}
        </span>
      ),
      children: <BackgroundTaskList />,
    },
    {
      key: 'download',
      label: (
        <span className="flex items-center gap-1.5">
          <DownloadOutlined />
          下载
          {activeDownloadCount > 0 && (
            <span className="bg-blue-500 text-white text-xs px-1.5 py-0.5 rounded-full min-w-5 text-center">
              {activeDownloadCount}
            </span>
          )}
        </span>
      ),
      children: <DownloadTaskList />,
    },
  ]

  return (
    <div className="fixed bottom-24 right-6 z-50 animate-in fade-in slide-in-from-bottom-4 duration-200">
      <Card
        className="shadow-lg"
        styles={{
          body: { padding: 0 },
          header: { padding: '8px 12px', minHeight: 'auto' },
        }}
        title={
          <div className="flex items-center justify-between">
            <Text strong>任务中心</Text>
            <div
              onClick={() => setOpen(false)}
              className="px-1 hover:bg-gray-100 rounded transition-colors"
            >
              <CloseOutlined className="text-gray-500" />
            </div>
          </div>
        }
        style={{ width: 360 }}
      >
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as 'background' | 'download')}
          items={tabItems}
          size="small"
          className="task-center-tabs"
          tabBarStyle={{ margin: 0, paddingLeft: 12, paddingRight: 12 }}
        />
      </Card>
    </div>
  )
}

export default TaskCenterPanel
