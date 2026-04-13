import React from 'react'
import { Clock, CheckCircle, Bug, Zap } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { compareVersions, versionUpdates } from '@/config/versionConfig'
import { parseIssueReferences } from '@/utils/issueParser'

interface VersionUpdateModalProps {
  visible: boolean
  onClose: () => void
  onRemindLater: () => void
  fromVersion: string
  toVersion: string
}

const VersionUpdateModal: React.FC<VersionUpdateModalProps> = ({
  visible,
  onClose,
  onRemindLater,
  fromVersion,
  toVersion,
}) => {
  const relevantUpdates = versionUpdates
    .filter(
      (update) =>
        compareVersions(update.version, fromVersion) > 0 &&
        compareVersions(update.version, toVersion) <= 0
    )
    .sort((a, b) => compareVersions(b.version, a.version))

  const renderUpdateItem = (
    type: 'features' | 'fixes' | 'improvements',
    items: string[] = []
  ) => {
    if (items.length === 0) return null

    const config = {
      features: { Icon: Zap, color: 'text-blue-600', title: '新功能' },
      fixes: { Icon: Bug, color: 'text-red-600', title: '问题修复' },
      improvements: { Icon: CheckCircle, color: 'text-green-600', title: '优化改进' },
    }

    const { Icon, color, title } = config[type]

    return (
      <div className="mb-4">
        <div className="flex items-center gap-1.5">
          <Icon className={`h-4 w-4 ${color}`} />
          <strong className={`text-sm ${color}`}>{title}：</strong>
        </div>
        <ul className="ml-6 mt-2 space-y-1">
          {items.map((item, index) => (
            <li key={index} className="text-sm">
              {parseIssueReferences(item)}
            </li>
          ))}
        </ul>
      </div>
    )
  }

  return (
    <Dialog open={visible} onOpenChange={(o) => !o && onRemindLater()}>
      <DialogContent className="sm:max-w-180">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-blue-600" />
            <span>版本更新通知</span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 max-h-[70vh] overflow-y-auto py-2">
          <div className="text-center">
            <h4 className="text-lg font-semibold">欢迎使用 MC Admin v{toVersion}！</h4>
            <p className="text-sm text-muted-foreground mt-1">
              从 v{fromVersion} 到 v{toVersion} 的更新内容
            </p>
          </div>

          <Separator />

          {relevantUpdates.length > 0 ? (
            <div className="space-y-6">
              {relevantUpdates.map((update, idx) => (
                <div key={update.version} className="relative pl-8">
                  <div className="absolute left-0 top-1">
                    <Clock className="h-5 w-5 text-blue-600" />
                  </div>
                  {idx < relevantUpdates.length - 1 && (
                    <div className="absolute left-2.25 top-7 -bottom-6 w-px bg-border" />
                  )}
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="secondary" className="bg-blue-100 text-blue-700 border-blue-200">
                        v{update.version}
                      </Badge>
                      <span className="text-xs text-muted-foreground">{update.date}</span>
                    </div>
                    <h5 className="text-base font-semibold mb-2">
                      {parseIssueReferences(update.title)}
                    </h5>
                    <p className="text-sm text-muted-foreground mb-3">
                      {parseIssueReferences(update.description)}
                    </p>
                    <div className="ml-2">
                      {renderUpdateItem('features', update.features)}
                      {renderUpdateItem('improvements', update.improvements)}
                      {renderUpdateItem('fixes', update.fixes)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">暂无更新记录</div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onRemindLater}>
            稍后提醒我
          </Button>
          <Button onClick={onClose}>明白了</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default VersionUpdateModal
