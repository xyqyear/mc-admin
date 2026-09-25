import { useState } from 'react'
import { Alert, AlertTitle, AlertDescription } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/shared/ui/dialog'
import { MonacoDiffEditor } from '@/shared/editors/index'
import type { ConfigurationSnapshot } from '@/features/configuration/useConfigurationSession'

export function ConfigurationConflict<T>({ baseline, remote, draftDescription, needed, refresh, accept }: {
  baseline: ConfigurationSnapshot<T>
  remote: ConfigurationSnapshot<T>
  draftDescription: string
  needed: boolean
  refresh: () => Promise<ConfigurationSnapshot<T>>
  accept: (snapshot: ConfigurationSnapshot<T>) => void
}) {
  const [compared, setCompared] = useState<ConfigurationSnapshot<T> | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  if (!needed) return null

  const compare = async () => {
    setLoading(true)
    setError('')
    try { setCompared(await refresh()) }
    catch { setError('读取在线配置失败，草稿已保留。请重试比较。') }
    finally { setLoading(false) }
  }

  return <>
    <Alert variant="destructive">
      <AlertTitle>在线配置已变更</AlertTitle>
      <AlertDescription>
        本地草稿已保留。请比较编辑起点、最新在线配置和本地草稿，确认新的提交基准后再提交。
        <Button variant="outline" onClick={compare} disabled={loading}>比较并解决冲突</Button>
        {error && <span role="status">{error}</span>}
      </AlertDescription>
    </Alert>
    <Dialog open={!!compared} onOpenChange={open => { if (!open) setCompared(null) }}>
      <DialogContent className="sm:max-w-250 max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>比较配置并确认提交基准</DialogTitle></DialogHeader>
        <p className="text-sm">接受基准不会覆盖本地草稿，也不会提交配置。请在编辑器中合并需要保留的在线变更，然后重新提交。</p>
        <MonacoDiffEditor height="256px" language="yaml" original={baseline.description} modified={compared?.description ?? ''} originalTitle="编辑起点" modifiedTitle="最新在线配置" />
        <MonacoDiffEditor height="256px" language="yaml" original={compared?.description ?? ''} modified={draftDescription} originalTitle="最新在线配置" modifiedTitle="本地草稿" />
        {compared && compared.version !== remote.version && <p role="status">在线配置再次变化，请重新比较。</p>}
        {error && <p role="alert">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={() => setCompared(null)}>返回编辑</Button>
          <Button onClick={compare} disabled={loading}>刷新比较</Button>
          <Button disabled={!compared?.version || compared.version !== remote.version || loading || !!error} onClick={() => { if (compared) accept(compared); setCompared(null) }}>接受此版本为新基准</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </>
}
