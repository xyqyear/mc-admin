import { Card, CardHeader, CardTitle, CardContent } from '@/shared/ui/card'
import { Progress } from '@/shared/ui/progress'
import { SampleValue } from '@/features/monitoring/ui/SampleValue'
import type { Sample } from '@/features/monitoring/contracts'
import type { ServerInfo } from '../contracts'

const progressColor = (value: number) => value > 80 ? '**:data-[slot=progress-indicator]:bg-red-500'
  : value > 60 ? '**:data-[slot=progress-indicator]:bg-yellow-500'
    : '**:data-[slot=progress-indicator]:bg-green-500'

export default function ServerResourcesCard({ cpu, memory, serverInfo, failed }: {
  cpu?: Sample<number>
  memory?: Sample<number>
  serverInfo: ServerInfo
  failed?: boolean
}) {
  const memoryPercent = memory?.value != null && serverInfo.maxMemoryBytes > 0 ? memory.value / serverInfo.maxMemoryBytes * 100 : null
  return <Card>
    <CardHeader className="pb-3"><CardTitle className="text-base">系统资源使用情况</CardTitle></CardHeader>
    <CardContent className="grid grid-cols-2 gap-4">
      <div className="space-y-2 text-sm">
        <div>CPU 使用率</div>
        <SampleValue sample={cpu} failed={failed}>{value => `${value.toFixed(1)}%`}</SampleValue>
        {cpu?.value != null && <Progress value={Math.min(100, cpu.value)} className={progressColor(cpu.value)} />}
      </div>
      <div className="space-y-2 text-sm">
        <div>内存使用</div>
        <SampleValue sample={memory} failed={failed}>{value => `${(value / 1024 ** 3).toFixed(1)}GB / ${(serverInfo.maxMemoryBytes / 1024 ** 3).toFixed(1)}GB`}</SampleValue>
        {memoryPercent != null && <Progress value={Math.min(100, memoryPercent)} className={progressColor(memoryPercent)} />}
      </div>
    </CardContent>
  </Card>
}
