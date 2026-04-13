import React, { useState } from 'react'
import { Bug } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import DebugDialog from './DebugDialog'

const DebugTool: React.FC = () => {
  const [dialogOpen, setDialogOpen] = useState(false)

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
              onClick={() => setDialogOpen(true)}
            >
              <Bug className="h-4 w-4" />
              <span className="sr-only">调试工具</span>
            </Button>
          }
        />
        <TooltipContent side="right">调试工具</TooltipContent>
      </Tooltip>

      <DebugDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
      />
    </>
  )
}

export default DebugTool
