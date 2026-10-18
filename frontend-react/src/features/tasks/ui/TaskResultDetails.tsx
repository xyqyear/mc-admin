import { useState } from 'react'
import { Button } from '@/shared/ui/button'
import { useTask } from '../queries'
import { TaskResultFeedback } from './TaskResultFeedback'

const isRecord = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const itemText = (value: unknown) => typeof value === 'string' || typeof value === 'number' ? String(value) : undefined

function ResultItems({ result }: { result: Record<string, unknown> }) {
  const errors = Array.isArray(result.errors) ? result.errors : Array.isArray(result.results)
    ? result.results.filter(item => isRecord(item) && (item.success === false || item.status === 'failed' || item.error))
    : []
  const findings = Array.isArray(result.findings) ? result.findings : []
  return <>
    {errors.length > 0 && <section>
      <h4 className="font-medium text-destructive">逐项失败结果（{errors.length}）</h4>
      <ul className="space-y-2">{errors.map((item, index) => <li key={index} className="break-all rounded border p-2">
        {isRecord(item) ? <>
          <p>{itemText(item.path) ?? itemText(item.server_id) ?? `项目 ${index + 1}`}</p>
          <p className="text-destructive">{itemText(item.error) ?? itemText(item.message) ?? JSON.stringify(item)}</p>
        </> : String(item)}
      </li>)}</ul>
    </section>}
    {findings.length > 0 && <section>
      <h4 className="font-medium">自检结果（{findings.length}）</h4>
      <ul className="space-y-2">{findings.map((item, index) => <li key={index} className="break-all rounded border p-2">
        {isRecord(item) ? <>
          <p className="font-medium">{itemText(item.title) ?? `检查项 ${index + 1}`}{itemText(item.server_id) ? ` · ${itemText(item.server_id)}` : ''}</p>
          <p>{itemText(item.message)}</p>
          {Array.isArray(item.remediation) && item.remediation.map((action, actionIndex) => <p key={actionIndex}>{String(action)}</p>)}
        </> : String(item)}
      </li>)}</ul>
    </section>}
    <details>
      <summary className="cursor-pointer">完整结果数据</summary>
      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(result, null, 2)}</pre>
    </details>
  </>
}

function LoadedResult({ taskId }: { taskId: string }) {
  const task = useTask(taskId)
  if (task.isAwaitingResult) return <TaskResultFeedback taskId={taskId} />
  if (task.isError) return <div role="alert">
    <p>无法读取任务结果：{task.error?.message}</p>
    <Button size="sm" variant="outline" disabled={task.isFetching} onClick={() => { void task.retryResult() }}>重试读取结果</Button>
  </div>
  if (!task.resultReady) return <p role="status">正在读取任务结果…</p>
  return task.data?.result ? <ResultItems result={task.data.result} /> : <p>任务已结束，没有额外结果。</p>
}

export function TaskResultDetails({ taskId }: { taskId: string }) {
  const [expanded, setExpanded] = useState(false)
  return <div className="space-y-2">
    <Button variant="outline" size="sm" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? '收起结果' : '查看结果'}</Button>
    {expanded && <LoadedResult taskId={taskId} />}
  </div>
}
