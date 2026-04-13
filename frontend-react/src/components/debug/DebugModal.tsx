import React, { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import { Bug, Trash2, Save, RotateCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, FieldLabel } from '@/components/ui/field'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { currentVersion } from '@/config/versionConfig'

interface DebugModalProps {
  visible: boolean
  onClose: () => void
}

const VERSION_STORAGE_KEY = 'mc-admin-last-seen-version'
const REMIND_TIME_STORAGE_KEY = 'mc-admin-remind-time'

const DebugModal: React.FC<DebugModalProps> = ({ visible, onClose }) => {
  const [version, setVersion] = useState('')
  const [remindTime, setRemindTime] = useState('')
  const [storedVersion, setStoredVersion] = useState('')
  const [storedRemindTime, setStoredRemindTime] = useState('')

  const refreshData = useCallback(() => {
    const v = localStorage.getItem(VERSION_STORAGE_KEY) || ''
    const r = localStorage.getItem(REMIND_TIME_STORAGE_KEY) || ''
    setStoredVersion(v)
    setStoredRemindTime(r)
    setVersion(v)
    setRemindTime(r)
  }, [])

  useEffect(() => {
    if (visible) {
      refreshData()
    }
  }, [visible, refreshData])

  const handleSaveVersion = () => {
    if (version) {
      localStorage.setItem(VERSION_STORAGE_KEY, version)
      toast.success(`版本已设置为: ${version}`)
      refreshData()
    }
  }

  const handleSaveRemindTime = () => {
    if (remindTime) {
      try {
        const date = new Date(remindTime)
        if (isNaN(date.getTime())) {
          toast.error('无效的日期格式，请使用 ISO 格式 (YYYY-MM-DDTHH:mm:ss.sssZ)')
          return
        }
        localStorage.setItem(REMIND_TIME_STORAGE_KEY, date.toISOString())
        toast.success(`提醒时间已设置为: ${date.toLocaleString()}`)
        refreshData()
      } catch {
        toast.error('无效的日期格式')
      }
    }
  }

  const handleClearVersion = () => {
    localStorage.removeItem(VERSION_STORAGE_KEY)
    toast.success('版本信息已清空')
    refreshData()
  }

  const handleClearRemindTime = () => {
    localStorage.removeItem(REMIND_TIME_STORAGE_KEY)
    toast.success('提醒时间已清空')
    refreshData()
  }

  const handleClearAll = () => {
    localStorage.removeItem(VERSION_STORAGE_KEY)
    localStorage.removeItem(REMIND_TIME_STORAGE_KEY)
    toast.success('所有调试数据已清空')
    refreshData()
  }

  const handleSetCurrentTime = () => {
    const now = new Date().toISOString()
    setRemindTime(now)
    localStorage.setItem(REMIND_TIME_STORAGE_KEY, now)
    toast.success('已设置为当前时间')
    refreshData()
  }

  const handleSetOneHourAgo = () => {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString()
    setRemindTime(oneHourAgo)
    localStorage.setItem(REMIND_TIME_STORAGE_KEY, oneHourAgo)
    toast.success('已设置为一小时前，刷新页面将触发版本提醒')
    refreshData()
  }

  return (
    <Dialog open={visible} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-150">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bug className="h-5 w-5 text-orange-500" />
            <span>调试工具</span>
            <span className="text-sm font-normal text-muted-foreground">(仅开发环境)</span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 max-h-[70vh] overflow-y-auto">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">当前信息</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div>
                <strong>当前版本：</strong>
                <code className="ml-1 rounded bg-muted px-1 py-0.5 text-xs">{currentVersion}</code>
              </div>
              <div>
                <strong>存储版本：</strong>
                <code className="ml-1 rounded bg-muted px-1 py-0.5 text-xs">{storedVersion || '未设置'}</code>
              </div>
              <div>
                <strong>提醒时间：</strong>
                <code className="ml-1 rounded bg-muted px-1 py-0.5 text-xs">
                  {storedRemindTime ? new Date(storedRemindTime).toLocaleString() : '未设置'}
                </code>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Separator className="flex-1" />
              <span className="text-xs font-medium text-muted-foreground">版本管理</span>
              <Separator className="flex-1" />
            </div>

            <Field>
              <FieldLabel htmlFor="debug-version">设置存储版本</FieldLabel>
              <div className="flex gap-2">
                <Input
                  id="debug-version"
                  placeholder="例如: 1.0.0"
                  value={version}
                  onChange={(e) => setVersion(e.target.value)}
                  className="flex-1"
                />
                <Button onClick={handleSaveVersion}>
                  <Save className="mr-1 h-4 w-4" />
                  保存
                </Button>
                <Button variant="destructive" onClick={handleClearVersion}>
                  <Trash2 className="mr-1 h-4 w-4" />
                  清空
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">设置 localStorage 中存储的版本号，用于测试版本更新提醒</p>
            </Field>
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Separator className="flex-1" />
              <span className="text-xs font-medium text-muted-foreground">提醒时间管理</span>
              <Separator className="flex-1" />
            </div>

            <Field>
              <FieldLabel htmlFor="debug-remind">设置提醒时间</FieldLabel>
              <div className="flex gap-2">
                <Input
                  id="debug-remind"
                  placeholder="例如: 2024-01-01T12:00:00.000Z"
                  value={remindTime}
                  onChange={(e) => setRemindTime(e.target.value)}
                  className="flex-1"
                />
                <Button onClick={handleSaveRemindTime}>
                  <Save className="mr-1 h-4 w-4" />
                  保存
                </Button>
                <Button variant="destructive" onClick={handleClearRemindTime}>
                  <Trash2 className="mr-1 h-4 w-4" />
                  清空
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">设置 localStorage 中的提醒时间 (ISO 格式)</p>
            </Field>

            <Field>
              <FieldLabel>快速设置</FieldLabel>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={handleSetCurrentTime}>
                  设为当前时间
                </Button>
                <Button size="sm" onClick={handleSetOneHourAgo}>
                  设为一小时前（触发提醒）
                </Button>
              </div>
            </Field>
          </div>

          <Separator />

          <div className="text-sm text-muted-foreground">
            <strong className="text-foreground">使用说明：</strong>
            <ul className="mt-2 space-y-1">
              <li>• 修改存储版本为较低版本（如 1.0.0），刷新页面测试版本更新提醒</li>
              <li>• 设置提醒时间为一小时前，刷新页面测试&quot;稍后提醒&quot;功能</li>
              <li>• 清空所有数据可重置为初始状态</li>
            </ul>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={refreshData}>
            <RotateCw className="mr-1 h-4 w-4" />
            刷新数据
          </Button>
          <Button variant="destructive" onClick={handleClearAll}>
            <Trash2 className="mr-1 h-4 w-4" />
            清空所有
          </Button>
          <Button onClick={onClose}>关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default DebugModal
