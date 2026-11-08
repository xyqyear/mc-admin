import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { GitCompareArrows, Save, Settings, Undo2 } from 'lucide-react'
import { toast } from 'sonner'
import type { SettingsResource } from '@/features/settings/api'
import { useSettings } from '@/features/settings/queries'
import { useSettingsCommands } from '@/features/settings/commands'
import { useEditorDraft } from '@/shared/hooks/useEditorDraft'
import { useConfirm } from '@/shared/hooks/useConfirm'
import PageHeader from '@/shared/layout/PageHeader'
import LoadingSpinner from '@/shared/layout/LoadingSpinner'
import RefreshButton from '@/shared/components/RefreshButton'
import { MonacoDiffEditor } from '@/shared/editors'
import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/ui/dialog'

interface Props<T> {
  title: string
  resource: SettingsResource<T>
  children: (value: T, onChange: (value: T) => void) => ReactNode
  afterSave?: () => Promise<void>
}

export default function SettingsEditor<T>({ title, resource, children, afterSave }: Props<T>) {
  const formId = useId()
  const query = useSettings(resource)
  const editor = useEditorDraft(resource.key, query.data)
  const commands = useSettingsCommands(resource)
  const { confirm, confirmDialog } = useConfirm()
  const [comparison, setComparison] = useState<{ original: T; draft: T; submit: boolean }>()
  const pending = commands.save.isPending || commands.reset.isPending
  const read = async () => {
    const result = await query.refetch({ throwOnError: true })
    if (result.data === undefined) throw new Error('配置读取失败')
    return result.data
  }
  const reload = () => confirm({
    title: '重新载入配置', description: '重新载入将丢弃当前未保存的更改。',
    onConfirm: async () => {
      try { editor.reset(await read()); toast.success('配置已重新载入') }
      catch { toast.error('重新载入失败，已保留编辑内容') }
    },
  })
  const reset = () => confirm({
    title: '重置为默认配置', description: '确定要覆盖此页面的设置并恢复默认值吗？', variant: 'destructive',
    onConfirm: async () => {
      try { editor.reset(await commands.reset.mutateAsync()); toast.success('配置已重置') }
      catch { return }
    },
  })
  const compare = async (submit: boolean) => {
    if (editor.draft === undefined || query.data === undefined) return
    const draft = editor.draft
    let original = query.data
    try { original = await read() } catch { toast.warning('获取最新配置失败，使用当前缓存进行对比') }
    setComparison({ original, draft, submit })
  }
  const save = async () => {
    if (!comparison) return
    try {
      editor.reset(await commands.save.mutateAsync(comparison.draft))
      setComparison(undefined)
      toast.success('配置已保存')
      await afterSave?.()
    } catch { return }
  }
  const submit = (event: FormEvent) => { event.preventDefault(); void compare(true) }
  return <div className="space-y-4">
    <PageHeader title={title} icon={<Settings className="h-5 w-5" />} actions={editor.ready && <>
      <Button type="button" variant="outline" disabled={pending} onClick={() => void compare(false)}><GitCompareArrows />差异对比</Button>
      <RefreshButton onClick={reload} isRefreshing={query.isFetching} label="重新载入" />
      <Button type="button" variant="destructive" disabled={pending} onClick={reset}><Undo2 />重置默认</Button>
      <Button type="submit" form={formId} disabled={pending}><Save />保存设置</Button>
    </>} />
    {query.isPending && <LoadingSpinner height="16rem" />}
    {query.isError && !editor.ready && <Alert variant="destructive"><AlertTitle>配置加载失败</AlertTitle><AlertDescription>请重试后继续编辑。<Button type="button" variant="outline" onClick={() => void query.refetch()}>重试</Button></AlertDescription></Alert>}
    {editor.ready && editor.draft !== undefined && <form id={formId} onSubmit={submit}>
      <fieldset disabled={pending} className="space-y-5">{children(editor.draft, editor.setDraft)}</fieldset>
    </form>}
    <Dialog open={Boolean(comparison)} onOpenChange={open => { if (!open && !pending) setComparison(undefined) }}>
      <DialogContent className="sm:max-w-5xl">
        <DialogHeader><DialogTitle>{comparison?.submit ? '提交配置更改' : '配置差异对比'}</DialogTitle><DialogDescription>左侧为服务器配置，右侧为本次编辑内容。</DialogDescription></DialogHeader>
        {comparison && <MonacoDiffEditor height="50vh" language="json" original={JSON.stringify(comparison.original, null, 2)} modified={JSON.stringify(comparison.draft, null, 2)} />}
        <DialogFooter><Button type="button" variant="outline" disabled={pending} onClick={() => setComparison(undefined)}>取消</Button>{comparison?.submit && <Button type="button" disabled={pending} onClick={() => void save()}>确认提交</Button>}</DialogFooter>
      </DialogContent>
    </Dialog>
    {confirmDialog}
  </div>
}

export function SettingsSection({ title, children }: { title: string; children: ReactNode }) {
  return <Card><CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader><CardContent className="space-y-5">{children}</CardContent></Card>
}
