import React, { useState } from 'react'
import { Bug } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import DebugModal from './DebugModal'

const DebugTool: React.FC = () => {
  const [modalVisible, setModalVisible] = useState(false)

  if (import.meta.env.MODE !== 'development') {
    return null
  }

  return (
    <>
      <Tooltip>
        <TooltipTrigger
          className="inline-flex"
          render={
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setModalVisible(true)}
            >
              <Bug className="h-4 w-4" />
              <span className="sr-only">调试工具</span>
            </Button>
          }
        />
        <TooltipContent side="right">调试工具</TooltipContent>
      </Tooltip>

      <DebugModal
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
      />
    </>
  )
}

export default DebugTool
