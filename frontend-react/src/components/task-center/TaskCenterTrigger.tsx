import React from 'react'
import { FloatButton } from 'antd'
import { UnorderedListOutlined } from '@ant-design/icons'
import { useTaskCenterStore } from '@/stores/useTaskCenterStore'
import { useTaskQueries } from '@/hooks/queries/base/useTaskQueries'
import { useDownloadTasks } from '@/stores/useDownloadStore'

const TaskCenterTrigger: React.FC = () => {
  const { isOpen, toggleOpen } = useTaskCenterStore()
  const { useActiveTasks } = useTaskQueries()
  const { data: activeTasks } = useActiveTasks()
  const downloadTasks = useDownloadTasks()

  // Count all active tasks
  const activeBackgroundCount = activeTasks?.length || 0
  const activeDownloadCount = downloadTasks.filter(
    (t) => t.status === 'downloading'
  ).length
  const totalActiveCount = activeBackgroundCount + activeDownloadCount

  return (
    <FloatButton
      icon={<UnorderedListOutlined />}
      tooltip={isOpen ? undefined : '任务中心'}
      badge={totalActiveCount > 0 ? { count: totalActiveCount } : undefined}
      onClick={toggleOpen}
      type={isOpen ? 'primary' : 'default'}
    />
  )
}

export default TaskCenterTrigger
