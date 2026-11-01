import { Card, CardHeader, CardTitle, CardContent } from '@/shared/ui/card'
import { SampleValue } from '@/features/monitoring/ui/SampleValue'
import type { ByteCounters, Sample } from '@/features/monitoring/contracts'

export default function ServerIOStatsCard({ disk, network, failed }: {
  disk?: Sample<ByteCounters>
  network?: Sample<ByteCounters>
  failed?: boolean
}) {
  return <Card>
    <CardHeader className="pb-3"><CardTitle className="text-base">I/O 统计（累计）</CardTitle></CardHeader>
    <CardContent className="grid grid-cols-2 gap-4 text-sm">
      <div className="space-y-4">
        <div>磁盘读取：<SampleValue sample={disk} failed={failed}>{value => `${(value.read / 1024 ** 2).toFixed(1)}MB`}</SampleValue></div>
        <div>磁盘写入：<SampleValue sample={disk} failed={failed}>{value => `${(value.write / 1024 ** 2).toFixed(1)}MB`}</SampleValue></div>
      </div>
      <div className="space-y-4">
        <div>网络接收：<SampleValue sample={network} failed={failed}>{value => `${(value.read / 1024 ** 2).toFixed(1)}MB`}</SampleValue></div>
        <div>网络发送：<SampleValue sample={network} failed={failed}>{value => `${(value.write / 1024 ** 2).toFixed(1)}MB`}</SampleValue></div>
      </div>
    </CardContent>
  </Card>
}
