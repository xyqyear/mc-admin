import React, { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  History,
  Info,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  XCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { StatusBadge, type BadgeTone } from '@/components/common/StatusBadge'
import { EmptyState } from '@/components/common/EmptyState'
import PageHeader from '@/components/layout/PageHeader'
import {
  useSelfCheckRun,
  useSelfCheckStatus,
} from '@/hooks/queries/base/useSelfCheckQueries'
import { useSelfCheckMutations } from '@/hooks/mutations/useSelfCheckMutations'
import { useEventStream } from '@/hooks/useEventStream'
import type {
  SelfCheckCatalogItem,
  SelfCheckCurrentState,
  SelfCheckFinding,
  SelfCheckStatusResponse,
  SelfCheckRunDetail,
  SelfCheckRunEvent,
  SelfCheckRunResult,
  SelfCheckRunStatus,
  SelfCheckRunSummaryRecord,
  SelfCheckSeverity,
  SelfCheckSummary,
} from '@/hooks/api/selfCheckApi'
import { queryKeys } from '@/utils/api'
import { formatDateTime } from '@/utils/formatUtils'
import { cn } from '@/lib/utils'

type DisplayFinding = SelfCheckFinding & { running?: boolean }

const emptyCatalog: SelfCheckCatalogItem[] = []

const emptySummary: SelfCheckSummary = {
  total: 0,
  passed: 0,
  skipped: 0,
  info: 0,
  warning: 0,
  critical: 0,
  failed: 0,
  status: 'success',
}

const statusTone: Record<SelfCheckRunStatus, BadgeTone> = {
  success: 'success',
  warning: 'warning',
  critical: 'danger',
}

const severityTone: Record<SelfCheckSeverity, BadgeTone> = {
  success: 'success',
  info: 'info',
  warning: 'warning',
  critical: 'danger',
}

const statusLabel: Record<SelfCheckRunStatus, string> = {
  success: '正常',
  warning: '警告',
  critical: '严重',
}

const severityLabel: Record<SelfCheckSeverity, string> = {
  success: '通过',
  info: '信息',
  warning: '警告',
  critical: '严重',
}

function findingSortRank(finding: DisplayFinding) {
  if (
    finding.status === 'failed' ||
    finding.status === 'critical' ||
    finding.severity === 'critical'
  ) {
    return 0
  }
  if (finding.status === 'warning' || finding.severity === 'warning') {
    return 1
  }
  if (
    finding.running ||
    finding.status === 'info' ||
    finding.status === 'skipped' ||
    finding.severity === 'info'
  ) {
    return 2
  }
  return 3
}

function sortFindings(findings: DisplayFinding[]) {
  return findings
    .map((finding, index) => ({ finding, index }))
    .sort((left, right) => {
      const rankDelta = findingSortRank(left.finding) - findingSortRank(right.finding)
      return rankDelta || left.index - right.index
    })
    .map((item) => item.finding)
}

function findingCardToneClass(finding: DisplayFinding) {
  if (
    finding.status === 'failed' ||
    finding.status === 'critical' ||
    finding.severity === 'critical'
  ) {
    return 'bg-red-50/90 ring-red-200/80 dark:bg-red-950/30 dark:ring-red-900/70'
  }
  if (finding.status === 'warning' || finding.severity === 'warning') {
    return 'bg-yellow-50/90 ring-yellow-200/80 dark:bg-yellow-950/30 dark:ring-yellow-900/70'
  }
  if (
    finding.running ||
    finding.status === 'info' ||
    finding.status === 'skipped' ||
    finding.severity === 'info'
  ) {
    return 'bg-blue-50/90 ring-blue-200/80 dark:bg-blue-950/30 dark:ring-blue-900/70'
  }
  return 'bg-green-50/90 ring-green-200/80 dark:bg-green-950/30 dark:ring-green-900/70'
}

const triggerLabel: Record<string, string> = {
  manual: '手动自检',
  scheduled: '自动巡检',
  server_created: '创建服务器后',
  server_populated: '填充服务器文件后',
  world_restored: '恢复世界后',
  world_rolled_back: '回档后',
}

const evidenceKeyLabel: Record<string, string> = {
  adoption_errors: '接管检查错误',
  created_at: '创建时间',
  database_only: '仅存在于数据库',
  deactivation_preview: '下线预览',
  description: '描述',
  dns_records_to_add: '待新增 DNS 记录',
  dns_records_to_remove: '待删除 DNS 记录',
  dns_records_to_update: '待更新 DNS 记录',
  error: '错误',
  errors: '扫描错误',
  files: '文件',
  servers: '服务器',
  filesystem_only: '仅存在于文件系统',
  gid: '用户组 ID',
  kind: '类型',
  lock_key: '锁键',
  max_age_minutes: '最大年龄分钟数',
  missing: '缺失项',
  mismatched: '不一致数量',
  mode: '权限位',
  mods_dir: 'Mods 目录',
  name: '名称',
  open_session_count: '未关闭会话数',
  output: '输出',
  path: '路径',
  restart_cronjob_count: '重启定时任务数',
  restoration_id: '恢复记录 ID',
  root: '根目录',
  router_routes_to_add: '待新增 MC Router 路由',
  router_routes_to_remove: '待删除 MC Router 路由',
  router_routes_to_update: '待更新 MC Router 路由',
  root_uid: '根目录用户 ID',
  samples: '样本',
  scanned: '已扫描数量',
  server_id: '服务器 ID',
  snapshot_id: '快照 ID',
  snapshot_time: '快照时间',
  started_at: '开始时间',
  threshold_percent: '阈值百分比',
  total_bytes: '总字节数',
  truncated: '是否截断',
  uid: '用户 ID',
  usage_percent: '使用率百分比',
  used_bytes: '已用字节数',
  user_id: '用户 ID',
}

const lockKindLabel: Record<string, string> = {
  backup: '备份',
  restore: '恢复',
}

function getTriggerLabel(trigger: string) {
  return triggerLabel[trigger] ?? trigger
}

function localizeEvidence(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => localizeEvidence(item))
  }

  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        evidenceKeyLabel[key] ?? key,
        key === 'kind' && typeof item === 'string'
          ? lockKindLabel[item] ?? item
          : localizeEvidence(item),
      ])
    )
  }

  if (typeof value === 'boolean') {
    return value ? '是' : '否'
  }

  if (value === null) {
    return '无'
  }

  return value
}

function summarizeFindings(findings: SelfCheckFinding[]): SelfCheckSummary {
  const warning = findings.filter((finding) => finding.severity === 'warning').length
  const critical = findings.filter((finding) => finding.severity === 'critical').length
  const failed = findings.filter((finding) => finding.status === 'failed').length
  return {
    total: findings.length,
    passed: findings.filter((finding) => finding.status === 'passed').length,
    skipped: findings.filter((finding) => finding.status === 'skipped').length,
    info: findings.filter((finding) => finding.severity === 'info' && finding.status !== 'skipped').length,
    warning,
    critical,
    failed,
    status: critical || failed ? 'critical' : warning ? 'warning' : 'success',
  }
}

function getProblemCount(summary: SelfCheckSummary) {
  return summary.warning + Math.max(summary.critical, summary.failed)
}

function patchCurrentState(
  status: SelfCheckStatusResponse | undefined,
  result: SelfCheckRunResult,
): SelfCheckStatusResponse | undefined {
  if (!status?.current_state || result.scope !== 'check' || !result.check_id) {
    return status
  }

  const findings = [
    ...status.current_state.findings.filter(
      (finding) => finding.check_id !== result.check_id
    ),
    ...result.findings,
  ]
  const summary = summarizeFindings(findings)

  return {
    ...status,
    current_state: {
      ...status.current_state,
      status: summary.status,
      updated_at: result.finished_at,
      source_run_id: result.id,
      summary,
      findings,
    },
    runs: [
      {
        id: result.id,
        trigger: result.trigger,
        scope: result.scope,
        check_id: result.check_id,
        status: result.status,
        started_at: result.started_at,
        finished_at: result.finished_at,
        duration_ms: result.duration_ms,
        summary: result.summary,
        requested_by_user_id: null,
        error_message: result.error_message,
      },
      ...status.runs.filter((run) => run.id !== result.id),
    ].slice(0, 10),
    total: status.total + (status.runs.some((run) => run.id === result.id) ? 0 : 1),
  }
}

function SummaryStrip({ summary }: { summary: SelfCheckSummary }) {
  const items = [
    { label: '通过', value: summary.passed, tone: 'success' as BadgeTone },
    { label: '信息 / 跳过', value: summary.info + summary.skipped, tone: 'info' as BadgeTone },
    { label: '警告', value: summary.warning, tone: 'warning' as BadgeTone },
    { label: '失败 / 严重', value: Math.max(summary.failed, summary.critical), tone: 'danger' as BadgeTone },
  ]

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-card px-3 py-2">
      {items.map((item) => (
        <div key={item.label} className="flex min-w-32 items-center justify-between gap-3 rounded-sm bg-muted/40 px-3 py-2">
          <span className="text-sm text-muted-foreground">{item.label}</span>
          <StatusBadge tone={item.tone} badgeStyle="soft" className="tabular-nums">
            {item.value}
          </StatusBadge>
        </div>
      ))}
      <div className="ml-auto text-sm text-muted-foreground">
        共 {summary.total} 项
      </div>
    </div>
  )
}

function statusIcon(finding: DisplayFinding) {
  if (finding.running) return <Spinner className="h-4 w-4" />
  if (finding.severity === 'success') return <CheckCircle2 className="h-4 w-4 text-green-600" />
  if (finding.severity === 'info') return <Info className="h-4 w-4 text-blue-600" />
  if (finding.severity === 'warning') return <AlertTriangle className="h-4 w-4 text-yellow-600" />
  return <XCircle className="h-4 w-4 text-red-600" />
}

function FindingCard({
  finding,
  canRerun,
  rerunning,
  onRerun,
}: {
  finding: DisplayFinding
  canRerun: boolean
  rerunning: boolean
  onRerun: () => void
}) {
  const hasDetails =
    finding.remediation.length > 0 || Object.keys(finding.evidence ?? {}).length > 0
  const tone = finding.running ? 'neutral' : severityTone[finding.severity]

  return (
    <Card
      className={cn(
        'gap-0 overflow-hidden py-0',
        findingCardToneClass(finding),
        finding.running && 'ring-primary/50'
      )}
    >
      <CardContent className="px-3 py-2.5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex min-w-0 flex-1 gap-3">
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted">
              {statusIcon(finding)}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-medium leading-6">{finding.title}</h3>
                <StatusBadge tone={tone} badgeStyle="soft">
                  {finding.running ? '检测中' : severityLabel[finding.severity]}
                </StatusBadge>
                {finding.status === 'skipped' && (
                  <StatusBadge tone="info" badgeStyle="soft">
                    跳过
                  </StatusBadge>
                )}
                {finding.server_id && (
                  <Badge variant="outline">{finding.server_id}</Badge>
                )}
              </div>
              <p className="mt-1 break-words text-sm text-muted-foreground">
                {finding.message}
              </p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1">
            {canRerun && (
              <Tooltip>
                <TooltipTrigger>
                  <span>
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={onRerun}
                      disabled={rerunning || finding.running}
                    >
                      {rerunning ? <Spinner /> : <RefreshCw />}
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>重新检测此项</TooltipContent>
              </Tooltip>
            )}
          </div>
        </div>

        {hasDetails && (
          <>
            <Separator className="my-2" />
            <div className="grid gap-3 text-sm md:grid-cols-2">
              {finding.remediation.length > 0 && (
                <div>
                  <div className="mb-1 font-medium">处理建议</div>
                  <div className="space-y-1 text-muted-foreground">
                    {finding.remediation.map((item) => (
                      <div key={item}>{item}</div>
                    ))}
                  </div>
                </div>
              )}
              {Object.keys(finding.evidence ?? {}).length > 0 && (
                <div>
                  <div className="mb-1 font-medium">证据</div>
                  <pre className="max-h-48 overflow-auto rounded-md bg-muted p-2 text-xs text-muted-foreground">
                    {JSON.stringify(localizeEvidence(finding.evidence), null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function HistoryRow({
  run,
  selected,
  onSelect,
  checkLabel,
}: {
  run: SelfCheckRunSummaryRecord
  selected: boolean
  onSelect: () => void
  checkLabel?: string
}) {
  const problemCount = getProblemCount(run.summary)
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'w-full rounded-md border p-3 text-left transition-colors hover:bg-muted/50',
        selected && 'border-primary bg-muted'
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <StatusBadge tone={statusTone[run.status]} badgeStyle="soft">
          {statusLabel[run.status]}
        </StatusBadge>
        <span className="text-xs text-muted-foreground">
          {run.scope === 'check' ? '单项检测' : getTriggerLabel(run.trigger)}
        </span>
      </div>
      <div className="mt-2 font-medium">{formatDateTime(run.finished_at)}</div>
      <div className="mt-1 flex flex-wrap gap-3 text-sm text-muted-foreground">
        <span>{run.summary.total} 项</span>
        <span>{problemCount} 个问题</span>
        <span>{run.duration_ms}ms</span>
      </div>
      {checkLabel && (
        <Badge variant="outline" className="mt-2">
          {checkLabel}
        </Badge>
      )}
    </button>
  )
}

const SelfCheck: React.FC = () => {
  const queryClient = useQueryClient()
  const statusQuery = useSelfCheckStatus()
  const { useRunSelfCheckItem } = useSelfCheckMutations()
  const runItemMutation = useRunSelfCheckItem()
  const [streaming, setStreaming] = useState(false)
  const [streamFindings, setStreamFindings] = useState<DisplayFinding[] | null>(null)
  const [streamResult, setStreamResult] = useState<SelfCheckRunResult | null>(null)
  const [streamStartedAt, setStreamStartedAt] = useState<string | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [rerunningCheckId, setRerunningCheckId] = useState<string | null>(null)

  const selectedRunQuery = useSelfCheckRun(selectedRunId)

  const currentState = statusQuery.data?.current_state ?? null
  const displayRun: SelfCheckRunResult | SelfCheckRunDetail | SelfCheckCurrentState | null =
    streamResult ?? selectedRunQuery.data ?? currentState
  const catalog = statusQuery.data?.catalog ?? emptyCatalog
  const checkLabelById = useMemo(
    () => new Map(catalog.map((item) => [item.check_id, item.title])),
    [catalog]
  )

  const displayFindings = useMemo<DisplayFinding[]>(() => {
    if (streamFindings) return sortFindings(streamFindings)
    return sortFindings(displayRun?.findings ?? [])
  }, [displayRun?.findings, streamFindings])

  const displaySummary = useMemo(
    () => streamFindings ? summarizeFindings(streamFindings.filter((finding) => !finding.running)) : displayRun?.summary ?? emptySummary,
    [displayRun?.summary, streamFindings]
  )

  const historyRuns = statusQuery.data?.runs ?? []
  const retentionDays = statusQuery.data?.retention_runs_keep_days ?? 14
  const selectedIsHistory = selectedRunId !== null

  useEffect(() => {
    if (streaming) return
    if (!streamResult) return
    setStreamFindings(null)
  }, [streamResult, streaming])

  useEventStream<SelfCheckRunEvent>({
    enabled: streaming,
    url: '/self-check/run/stream',
    method: 'POST',
    onEvent: (event) => {
      if (event.type === 'started') {
        setSelectedRunId(null)
        setStreamResult(null)
        setStreamStartedAt(event.started_at ?? null)
        setStreamFindings([])
        return
      }

      if (event.type === 'check_started' && event.check_id) {
        const item = catalog.find((catalogItem) => catalogItem.check_id === event.check_id)
        const runningFinding: DisplayFinding = {
          check_id: event.check_id,
          category: item?.category ?? 'self_check',
          severity: 'info',
          status: 'info',
          title: item?.title ?? '自检项',
          message: '检测中',
          evidence: {},
          remediation: [],
          created_at: new Date().toISOString(),
          running: true,
        }
        setStreamFindings((current) => {
          const next = (current ?? []).filter((finding) => finding.check_id !== event.check_id || !finding.running)
          return [...next, runningFinding]
        })
        return
      }

      if (event.type === 'check_finished' && event.check_id) {
        const findings = event.findings ?? []
        setStreamFindings((current) => {
          const next = (current ?? []).filter((finding) => finding.check_id !== event.check_id)
          return [...next, ...findings]
        })
        return
      }

      if (event.type === 'error') {
        if (event.findings?.length) {
          setStreamFindings((current) => [...(current ?? []), ...(event.findings ?? [])])
        }
        toast.error(event.message ?? '自检失败')
        return
      }

      if (event.type === 'completed' && event.result) {
        setStreamResult(event.result)
        setStreamFindings(event.result.findings)
        setStreaming(false)
        void queryClient.invalidateQueries({ queryKey: queryKeys.selfCheck.all })
        if (event.result.status === 'success') {
          toast.success('自检完成，未发现问题')
        } else {
          toast.warning('自检完成，发现需要处理的项目')
        }
      }
    },
    onError: (message) => {
      setStreaming(false)
      toast.error(`自检失败: ${message}`)
    },
    onClose: () => {
      setStreaming(false)
    },
  })

  const handleRun = () => {
    setSelectedRunId(null)
    setStreamResult(null)
    setStreamFindings(null)
    setStreaming(true)
  }

  const handleShowCurrentState = () => {
    setSelectedRunId(null)
    setStreamResult(null)
    setStreamFindings(null)
    setStreaming(false)
  }

  const handleRerunItem = async (finding: SelfCheckFinding) => {
    setRerunningCheckId(finding.check_id)
    try {
      const result = await runItemMutation.mutateAsync(finding.check_id)
      setStreamResult(null)
      setStreamFindings(null)
      setSelectedRunId(null)
      queryClient.setQueryData<SelfCheckStatusResponse>(
        queryKeys.selfCheck.status(),
        (current) => patchCurrentState(current, result)
      )
    } finally {
      setRerunningCheckId(null)
    }
  }

  const sourceLabel = selectedIsHistory
    ? '历史自检结果'
    : streaming
      ? '实时自检结果'
      : '当前自检状态'

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="系统自检"
        icon={<ShieldCheck />}
        actions={
          <div className="ml-auto flex items-center gap-2">
            <Button onClick={handleRun} disabled={streaming}>
              {streaming ? (
                <Spinner data-icon="inline-start" />
              ) : (
                <Play data-icon="inline-start" />
              )}
              立即自检
            </Button>
          </div>
        }
      />

      {statusQuery.error && (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>加载自检状态失败</AlertTitle>
          <AlertDescription>{statusQuery.error.message}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge tone={statusTone[displaySummary.status]} badgeStyle="soft">
          {statusLabel[displaySummary.status]}
        </StatusBadge>
        <div className="text-sm text-muted-foreground">
          {sourceLabel}
          {displayRun && 'updated_at' in displayRun && ` · ${formatDateTime(displayRun.updated_at)}`}
          {displayRun && 'finished_at' in displayRun && ` · ${formatDateTime(displayRun.finished_at)}`}
          {streaming && streamStartedAt && ` · 开始于 ${formatDateTime(streamStartedAt)}`}
          {displayRun && 'duration_ms' in displayRun && ` · ${displayRun.duration_ms}ms`}
        </div>
        {selectedIsHistory && (
          <Button variant="outline" size="sm" onClick={handleShowCurrentState}>
            <RotateCcw data-icon="inline-start" />
            回到当前状态
          </Button>
        )}
      </div>

      <SummaryStrip summary={displaySummary} />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex min-w-0 flex-col gap-3">
          {statusQuery.isLoading && !displayRun && !streaming ? (
            <div className="flex items-center justify-center py-16">
              <Spinner />
            </div>
          ) : displayFindings.length > 0 ? (
            displayFindings.map((finding, index) => (
              <FindingCard
                key={`${finding.check_id}-${finding.server_id ?? 'global'}-${index}-${finding.running ? 'running' : 'done'}`}
                finding={finding}
                canRerun={!streaming && !finding.running}
                rerunning={rerunningCheckId === finding.check_id}
                onRerun={() => void handleRerunItem(finding)}
              />
            ))
          ) : (
            <EmptyState
              icon={ShieldCheck}
              title="暂无自检结果"
              description="点击立即自检后会在这里显示每一个自检项"
            />
          )}
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-base font-medium">
            <History className="h-4 w-4" />
            历史记录
          </div>
          {statusQuery.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Spinner />
            </div>
          ) : historyRuns.length ? (
            <div className="flex flex-col gap-2">
              {historyRuns.map((run) => (
                <HistoryRow
                  key={run.id}
                  run={run}
                  selected={selectedRunId === run.id}
                  checkLabel={run.check_id ? checkLabelById.get(run.check_id) ?? '未知自检项' : undefined}
                  onSelect={() => {
                    setStreaming(false)
                    setStreamResult(null)
                    setStreamFindings(null)
                    setSelectedRunId(run.id)
                  }}
                />
              ))}
            </div>
          ) : (
              <EmptyState
                icon={CheckCircle2}
                title="暂无历史记录"
                description={`自检运行后会在这里保留 ${retentionDays} 天`}
              />
          )}
        </div>
      </div>
    </div>
  )
}

export default SelfCheck
