import { useState } from 'react'
import { Button } from '@/shared/ui/button'
import { Label } from '@/shared/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/shared/ui/dialog'
import { useDirectoryDownload } from '../../useDirectoryDownload'

export interface DirectoryDownloadRequest {
  paths: string[]
  basePath: string
}

export function DirectoryDownloadDialog({ serverId, request, onClose }: {
  serverId: string
  request: DirectoryDownloadRequest | null
  onClose: () => void
}) {
  const [layout, setLayout] = useState<'original' | 'flat'>('original')
  const download = useDirectoryDownload(serverId)
  return <Dialog open={!!request} onOpenChange={open => { if (!open) onClose() }}>
    <DialogContent>
      <DialogHeader><DialogTitle>下载到本地文件夹</DialogTitle></DialogHeader>
      <p className="text-sm text-muted-foreground">选择本地保存位置后，会创建独立的导出文件夹。所选文件夹会包含全部子文件。</p>
      <div className="space-y-2">
        <Label htmlFor="directory-download-layout">文件组织方式</Label>
        <Select value={layout} onValueChange={value => { if (value === 'original' || value === 'flat') setLayout(value) }} itemToStringLabel={value => value === 'flat' ? '平铺文件' : '保留原路径'}>
          <SelectTrigger id="directory-download-layout"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="original">保留原路径</SelectItem><SelectItem value="flat">平铺文件</SelectItem></SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">{layout === 'flat' ? '全部文件放在同一层，重名会自动调整；空目录不保留。' : `目录结构以 ${request?.basePath ?? '/'} 为基准，保留空目录。`}</p>
      </div>
      <div className="max-h-40 overflow-auto text-sm"><ul>{request?.paths.map(path => <li key={path}>{path}</li>)}</ul></div>
      {!download.supported && <p className="text-sm text-muted-foreground">{download.reason}</p>}
      <DialogFooter><Button variant="outline" onClick={onClose}>取消</Button><Button disabled={!download.supported} onClick={() => {
        if (!request) return
        void download.downloadToDirectory({ ...request, paths: [...request.paths], layout })
        onClose()
      }}>选择保存文件夹</Button></DialogFooter>
    </DialogContent>
  </Dialog>
}
