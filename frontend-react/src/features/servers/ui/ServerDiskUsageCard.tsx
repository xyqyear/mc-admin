import { Card, CardHeader, CardTitle, CardContent } from '@/shared/ui/card'
import { SampleValue } from '@/features/monitoring/ui/SampleValue'
import type { DiskUsage, Sample } from '@/features/monitoring/contracts'

export default function ServerDiskUsageCard({ sample, failed }: { sample?: Sample<DiskUsage>; failed?: boolean }) {
  const disk = sample?.value
  return <Card>
    <CardHeader className="pb-3"><CardTitle className="text-base">磁盘使用空间</CardTitle></CardHeader>
    <CardContent className="space-y-3 text-sm">
      <div>存档占用：<SampleValue sample={sample} failed={failed}>{value => `${(value.used / 1024 ** 3).toFixed(2)}GB`}</SampleValue></div>
      <div>可用空间：<SampleValue sample={sample} failed={failed}>{value => `${(value.available / 1024 ** 3).toFixed(2)}GB`}</SampleValue></div>
      <div>磁盘容量：<SampleValue sample={sample} failed={failed}>{value => `${(value.total / 1024 ** 3).toFixed(2)}GB`}</SampleValue></div>
      {disk && disk.total > 0 && <>
        <div className="h-2 w-full rounded-full bg-muted overflow-hidden flex">
          <div className="h-full bg-green-500 transition-all" style={{ width: `${Math.min(100, disk.used / disk.total * 100)}%` }} />
          <div className="h-full bg-yellow-500 transition-all" style={{ width: `${Math.max(0, (disk.total - disk.available - disk.used) / disk.total * 100)}%` }} />
        </div>
        <div className="text-xs text-muted-foreground flex flex-wrap items-center gap-4">
          <span className="flex items-center gap-1"><span className="inline-block size-3 bg-green-500 rounded" />该服务器使用</span>
          <span className="flex items-center gap-1"><span className="inline-block size-3 bg-yellow-500 rounded" />其他文件使用</span>
          <span>未填充部分为剩余空间</span>
        </div>
      </>}
    </CardContent>
  </Card>
}
