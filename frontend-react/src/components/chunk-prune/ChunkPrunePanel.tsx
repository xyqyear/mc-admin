import React, { useMemo } from 'react'
import { Ban, CheckCircle2, Play, RotateCcw, Trash2 } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type {
  ChunkPruneMode,
  ChunkPruneResultData,
} from '@/types/ChunkPrune'
import type { BackgroundTaskStatus } from '@/stores/useBackgroundTaskStore'
import type { ThresholdUnit } from './thresholdUnits'

const THRESHOLD_UNITS: ReadonlyArray<{ value: ThresholdUnit; label: string }> = [
  { value: 'seconds', label: '秒' },
  { value: 'minutes', label: '分钟' },
  { value: 'hours', label: '小时' },
]

export interface ChunkPrunePanelProps {
  thresholdValue: string
  thresholdUnit: ThresholdUnit
  thresholdSeconds: number
  mode: ChunkPruneMode
  previewStatus: BackgroundTaskStatus | 'idle'
  previewStarting: boolean
  previewProgress: number | null
  previewMessage: string | null
  previewResult: ChunkPruneResultData | null
  previewError: string | null
  applyStatus: BackgroundTaskStatus | 'idle'
  applyProgress: number | null
  applyMessage: string | null
  applyResult: ChunkPruneResultData | null
  applyError: string | null
  serverStopped: boolean
  canPreview: boolean
  canApply: boolean
  cancellingPreview: boolean
  cancellingApply: boolean
  onThresholdValueChange: (value: string) => void
  onThresholdUnitChange: (unit: ThresholdUnit) => void
  onModeChange: (mode: ChunkPruneMode) => void
  onPreview: () => void
  onCancelPreview: () => void
  onApply: () => void
  onCancelApply: () => void
}

const formatInt = (value: number | null | undefined): string =>
  typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString()
    : '0'

const phaseLabel = (phase: string | undefined): string => {
  if (phase === 'scan') return '扫描'
  if (phase === 'prune') return '删除'
  return phase || '处理'
}

const resultSummary = (result: ChunkPruneResultData | null): string => {
  if (!result) return '暂无结果'
  if (result.mode === 'regions') {
    return `${formatInt(result.regions_selected)} 个区域，${formatInt(
      result.chunks_selected,
    )} 个区块`
  }
  return `${formatInt(result.chunks_selected)} 个区块，覆盖 ${formatInt(
    result.regions_selected,
  )} 个区域`
}

const ChunkPrunePanel: React.FC<ChunkPrunePanelProps> = ({
  thresholdValue,
  thresholdUnit,
  thresholdSeconds,
  mode,
  previewStatus,
  previewStarting,
  previewProgress,
  previewMessage,
  previewResult,
  previewError,
  applyStatus,
  applyProgress,
  applyMessage,
  applyResult,
  applyError,
  serverStopped,
  canPreview,
  canApply,
  cancellingPreview,
  cancellingApply,
  onThresholdValueChange,
  onThresholdUnitChange,
  onModeChange,
  onPreview,
  onCancelPreview,
  onApply,
  onCancelApply,
}) => {
  const previewRunning = previewStarting || previewStatus === 'running'
  const applyRunning = applyStatus === 'running'
  const previewPercent = previewProgress ?? 0
  const applyPercent = applyProgress ?? 0
  const thresholdTicks = useMemo(
    () => Math.max(0, thresholdSeconds * 20),
    [thresholdSeconds],
  )

  return (
    <FieldGroup className="gap-4">
      <Field>
        <FieldLabel>清理阈值</FieldLabel>
        <div className="grid grid-cols-[1fr_92px] gap-2">
          <Input
            type="number"
            min={0}
            step={1}
            value={thresholdValue}
            disabled={previewRunning || applyRunning}
            onChange={(e) => onThresholdValueChange(e.target.value)}
          />
          <Select
            value={thresholdUnit}
            disabled={previewRunning || applyRunning}
            onValueChange={(v) => onThresholdUnitChange(v as ThresholdUnit)}
            itemToStringLabel={(v) =>
              THRESHOLD_UNITS.find((o) => o.value === v)?.label ?? String(v)
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {THRESHOLD_UNITS.map((unit) => (
                <SelectItem key={unit.value} value={unit.value}>
                  {unit.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <FieldDescription className="text-xs">
          {formatInt(thresholdSeconds)} 秒 / {formatInt(thresholdTicks)} tick
        </FieldDescription>
      </Field>

      <Field>
        <FieldLabel>清理模式</FieldLabel>
        <Tabs
          value={mode}
          onValueChange={(v) => {
            if (v === 'chunks' || v === 'regions') onModeChange(v)
          }}
        >
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger
              value="regions"
              disabled={previewRunning || applyRunning}
            >
              区域
            </TabsTrigger>
            <TabsTrigger
              value="chunks"
              disabled={previewRunning || applyRunning}
            >
              区块
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <FieldDescription className="text-xs">
          {mode === 'chunks'
            ? '扫描服务器所有维度，删除低活跃且未被领地保护的区块。'
            : '扫描服务器所有维度，只有整个区域都低活跃且没有领地时才删除。'}
        </FieldDescription>
      </Field>

      <div className="grid grid-cols-2 gap-2">
        <Button onClick={onPreview} disabled={!canPreview}>
          <Play className="mr-1 h-4 w-4" />
          预览
        </Button>
        <Button
          variant="outline"
          onClick={onCancelPreview}
          disabled={!previewRunning || previewStarting || cancellingPreview}
        >
          <Ban className="mr-1 h-4 w-4" />
          取消
        </Button>
      </div>

      {(previewRunning || previewProgress || previewResult || previewError) && (
        <div className="rounded border bg-background p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-sm font-medium">预览进度</span>
            <Badge variant={previewStatus === 'completed' ? 'secondary' : 'outline'}>
              {previewStarting
                ? '准备中'
                : previewStatus === 'completed'
                ? '已完成'
                : previewStatus === 'failed'
                  ? '失败'
                  : previewStatus === 'cancelled'
                    ? '已取消'
                    : '运行中'}
            </Badge>
          </div>
          <Progress value={previewPercent} className="mb-2" />
          <div className="text-xs text-muted-foreground">
            {previewMessage ||
              (previewStarting || previewStatus === 'running'
                ? '正在准备预览任务...'
                : phaseLabel('scan'))}
          </div>
          {previewResult && (
            <div className="mt-2 text-xs">
              <div className="font-medium">{resultSummary(previewResult)}</div>
              <div className="text-muted-foreground">
                已扫描 {formatInt(previewResult.regions_scanned)} 个区域文件，
                {formatInt(previewResult.chunks_scanned)} 个区块
              </div>
              {typeof previewResult.chunks_skipped_by_claims === 'number' && (
                <div className="text-muted-foreground">
                  领地保护跳过 {formatInt(previewResult.chunks_skipped_by_claims)} 个区块
                </div>
              )}
            </div>
          )}
          {previewError && (
            <div className="mt-2 text-xs text-destructive">{previewError}</div>
          )}
        </div>
      )}

      {!serverStopped && (
        <Alert>
          <AlertTitle>需要先停止服务器</AlertTitle>
          <AlertDescription>
            预览可以在当前状态运行，真实删除需要服务器停止后再执行。
          </AlertDescription>
        </Alert>
      )}

      <Button
        variant="destructive"
        onClick={onApply}
        disabled={!canApply}
        className="w-full"
      >
        <Trash2 className="mr-1 h-4 w-4" />
        删除预览中的服务器区块
      </Button>

      {(applyRunning || applyProgress || applyResult || applyError) && (
        <div className="rounded border bg-background p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-sm font-medium">删除进度</span>
            <Badge variant={applyStatus === 'completed' ? 'secondary' : 'outline'}>
              {applyStatus === 'completed'
                ? '已完成'
                : applyStatus === 'failed'
                  ? '失败'
                  : applyStatus === 'cancelled'
                    ? '已取消'
                    : '运行中'}
            </Badge>
          </div>
          <Progress value={applyPercent} className="mb-2" />
          <div className="text-xs text-muted-foreground">
            {applyMessage || phaseLabel('prune')}
          </div>
          {applyResult && (
            <div className="mt-2 flex items-center gap-1 text-xs text-green-600">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {resultSummary(applyResult)}
            </div>
          )}
          {applyError && (
            <div className="mt-2 text-xs text-destructive">{applyError}</div>
          )}
          {applyRunning && (
            <Button
              variant="outline"
              size="sm"
              onClick={onCancelApply}
              disabled={cancellingApply}
              className="mt-3 w-full"
            >
              <RotateCcw className="mr-1 h-3.5 w-3.5" />
              取消删除
            </Button>
          )}
        </div>
      )}
    </FieldGroup>
  )
}

export default ChunkPrunePanel
