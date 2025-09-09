import React, { useState } from 'react'
import { Button, Tooltip } from 'antd'
import { BugOutlined } from '@ant-design/icons'
import DebugModal from './DebugModal'

const DebugTool: React.FC = () => {
  const [modalVisible, setModalVisible] = useState(false)

  // 只在开发环境下显示
  if (import.meta.env.MODE !== 'development') {
    return null
  }

  return (
    <>
      <div className="p-2">
        <Tooltip title="调试工具" placement="right">
          <Button
            type="text"
            icon={<BugOutlined />}
            size="small"
            onClick={() => setModalVisible(true)}
            className="w-full flex items-center justify-center text-gray-500 hover:text-blue-500 hover:bg-blue-50"
          >
            调试
          </Button>
        </Tooltip>
      </div>

      <DebugModal
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
      />
    </>
  )
}

export default DebugTool