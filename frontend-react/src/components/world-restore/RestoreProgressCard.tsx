import React from 'react'
import { CheckCircle2, XCircle } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'

import type { RestoreProgressState } from './restoreProgress'

interface RestoreProgressCardProps {
  state: RestoreProgressState
  title?: string
}

export const RestoreProgressCard: React.FC<RestoreProgressCardProps> = ({
  state,
  title = '正在恢复',
}) => {
  return (
    <Card>
      <CardContent className="space-y-3 py-4">
        <div className="flex items-center gap-2">
          {state.error ? (
            <XCircle className="h-5 w-5 text-destructive" />
          ) : state.done ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-500" />
          ) : (
            <Spinner className="h-5 w-5" />
          )}
          <div className="font-medium">
            {state.error ? '恢复失败' : state.done ? '恢复完成' : title}
          </div>
          <div className="ml-auto text-sm text-muted-foreground tabular-nums">
            {Math.round(state.percent)}%
          </div>
        </div>
        <Progress value={state.percent} />
        <div className="text-sm text-muted-foreground">
          {state.error ?? state.message}
        </div>
        {state.log.length > 0 && (
          <pre className="mt-2 max-h-40 overflow-auto rounded-md border bg-muted/30 p-2 text-xs leading-relaxed">
            {state.log.join('\n')}
          </pre>
        )}
      </CardContent>
    </Card>
  )
}

export default RestoreProgressCard
