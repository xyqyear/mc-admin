import React, { useState } from 'react'
import { Bug } from 'lucide-react'
import { Button } from '@/components/ui/button'
import DebugModal from './DebugModal'

const DebugTool: React.FC = () => {
  const [modalVisible, setModalVisible] = useState(false)

  if (import.meta.env.MODE !== 'development') {
    return null
  }

  return (
    <>
      <div className="p-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setModalVisible(true)}
          className="w-full justify-center text-muted-foreground hover:text-blue-600 hover:bg-blue-50"
        >
          <Bug className="mr-1 h-4 w-4" />
          调试
        </Button>
      </div>

      <DebugModal
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
      />
    </>
  )
}

export default DebugTool
