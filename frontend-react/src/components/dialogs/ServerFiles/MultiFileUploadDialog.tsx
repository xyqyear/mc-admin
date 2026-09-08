import React, { useState } from 'react'
import { AlertTriangle, CheckCircle, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import type { OverwritePolicy } from '@/hooks/api/fileApi'
import { useMultiFileUpload, FILES_PER_BATCH } from '@/hooks/uploads/useMultiFileUpload'
import FileUploadTree from './FileUploadTree'
import ConflictTree from './ConflictTree'

interface MultiFileUploadDialogProps {
  open: boolean
  onCancel: () => void
  onComplete: () => void
  serverId: string
  basePath: string
  initialFiles?: File[]
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const MultiFileUploadDialog: React.FC<MultiFileUploadDialogProps> = ({
  open,
  onCancel,
  onComplete,
  serverId,
  basePath,
  initialFiles
}) => {
  const {
    uploadState, totalSize, check, start: handleStartUpload,
    setPolicy: handleOverwritePolicy, cancel: handleCancelUpload, close,
    back: backToSelection,
  } = useMultiFileUpload(open, serverId, basePath, initialFiles)
  const [conflictDecisions, setConflictDecisions] = useState<Record<string, boolean>>({})
  const handleCheckConflicts = () => {
    setConflictDecisions({})
    void check()
  }

  const handleConflictTreeCheck = (checked: React.Key[] | { checked: React.Key[]; halfChecked: React.Key[] }) => {
    const checkedKeys = Array.isArray(checked) ? checked : checked.checked
    const newDecisions: Record<string, boolean> = {}

    uploadState.conflicts.forEach(conflict => {
      newDecisions[conflict.path] = checkedKeys.includes(conflict.path)
    })

    setConflictDecisions(newDecisions)

    if (uploadState.overwritePolicy?.mode === 'per_file') {
      handleOverwritePolicy({
        mode: 'per_file',
        decisions: uploadState.conflicts.map(c => ({
          path: c.path,
          overwrite: newDecisions[c.path] ?? false
        }))
      })
    }
  }

  const getConflictCheckedKeys = (): React.Key[] => {
    return uploadState.conflicts
      .filter(conflict => conflictDecisions[conflict.path] ?? true)
      .map(conflict => conflict.path)
  }

  const renderContent = () => {
    switch (uploadState.step) {
      case 'checking':
      case 'select':
        return (
          <div className="space-y-4">
            {uploadState.files.length > 0 ? (
              <>
                <Card>
                  <CardContent className="pt-4">
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <div className="text-sm text-muted-foreground">文件数量</div>
                        <div className="text-2xl font-semibold">{uploadState.files.length}</div>
                      </div>
                      <div>
                        <div className="text-sm text-muted-foreground">总大小</div>
                        <div className="text-2xl font-semibold">{formatFileSize(totalSize)}</div>
                      </div>
                      <div>
                        <div className="text-sm text-muted-foreground">目标路径</div>
                        <div className="text-2xl font-semibold truncate">{basePath}</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                <FileUploadTree files={uploadState.files} />
              </>
            ) : (
              <Alert>
                <AlertTitle>未选择文件</AlertTitle>
                <AlertDescription>
                  请关闭该窗口并使用拖拽的方式选择要上传的文件或文件夹
                </AlertDescription>
              </Alert>
            )}
          </div>
        )

      case 'conflicts':
        return (
          <div className="space-y-4">
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>检测到文件冲突</AlertTitle>
              <AlertDescription>
                有 {uploadState.conflicts.length} 个文件将会覆盖现有文件，请选择处理方式
              </AlertDescription>
            </Alert>

            <div className="space-y-3">
              <h5 className="font-medium">覆盖策略</h5>
              <RadioGroup
                value={uploadState.overwritePolicy?.mode || ''}
                onValueChange={(mode) => {
                  if (!mode) return
                  handleOverwritePolicy({
                    mode: mode as OverwritePolicy['mode'],
                    decisions: mode === 'per_file'
                      ? uploadState.conflicts.map(c => ({
                          path: c.path,
                          overwrite: conflictDecisions[c.path] ?? true
                        }))
                      : undefined
                  })
                }}
              >
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="always_overwrite" id="always_overwrite" />
                  <Label htmlFor="always_overwrite">总是覆盖所有冲突文件</Label>
                </div>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="never_overwrite" id="never_overwrite" />
                  <Label htmlFor="never_overwrite">跳过所有冲突文件</Label>
                </div>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="per_file" id="per_file" />
                  <Label htmlFor="per_file">为每个文件单独选择</Label>
                </div>
              </RadioGroup>
            </div>

            {uploadState.overwritePolicy?.mode === 'per_file' && (
              <>
                <Separator />
                <ConflictTree
                  conflicts={uploadState.conflicts}
                  checkedKeys={getConflictCheckedKeys()}
                  onCheck={handleConflictTreeCheck}
                />
              </>
            )}
          </div>
        )

      case 'uploading':
        return (
          <div className="space-y-4">
            <div className="text-center space-y-2">
              <h4 className="text-lg font-semibold">正在上传文件...</h4>
              {uploadState.files.length > FILES_PER_BATCH && (
                <p className="text-sm text-muted-foreground">
                  分批上传，每批最多 {FILES_PER_BATCH} 个文件
                </p>
              )}
              <Progress value={uploadState.uploadProgress?.totalProgress || 0} />
              <p className="text-sm text-muted-foreground">
                {uploadState.uploadProgress?.totalProgress || 0}% ({uploadState.uploadProgress?.uploadedFiles || 0}/{uploadState.uploadProgress?.totalFiles || 0})
              </p>
            </div>

            <Card>
              <CardContent className="pt-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-sm text-muted-foreground">已上传</div>
                    <div className="text-2xl font-semibold">
                      {uploadState.uploadProgress?.uploadedFiles || 0}/{uploadState.uploadProgress?.totalFiles || 0}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-muted-foreground">传输大小</div>
                    <div className="text-2xl font-semibold">
                      {formatFileSize(uploadState.uploadProgress?.uploadedSize || 0)}
                      <span className="text-sm font-normal text-muted-foreground ml-1">
                        / {formatFileSize(uploadState.uploadProgress?.totalSize || 0)}
                      </span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )

      case 'complete':
        return (
          <div className="space-y-4">
            <div className="text-center space-y-2">
              <CheckCircle className="mx-auto h-12 w-12 text-green-500" />
              <h4 className="text-lg font-semibold text-green-600">上传完成！</h4>
            </div>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">上传结果</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="max-h-75 overflow-y-auto space-y-1">
                  {uploadState.results && Object.entries(uploadState.results).map(([filepath, result]) => (
                    <div key={filepath} className="flex justify-between items-center py-1">
                      <span className="text-sm truncate mr-2">{filepath}</span>
                      <Badge variant={
                        result.status === 'success' ? 'default' :
                          result.status === 'failed' ? 'destructive' : 'outline'
                      }>
                        {result.status === 'success' ? '成功' :
                          result.status === 'failed' ? '失败' : '跳过'}
                        {result.reason && ` (${result.reason})`}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )

      default:
        return null
    }
  }

  const renderFooter = () => {
    switch (uploadState.step) {
      case 'checking':
      case 'select':
        return (
          <>
            <Button variant="outline" onClick={handleDialogCancel}>取消</Button>
            <Button
              disabled={uploadState.files.length === 0 || uploadState.step === 'checking'}
              onClick={handleCheckConflicts}
            >
              {uploadState.step === 'checking' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              检查冲突并上传
            </Button>
          </>
        )
      case 'conflicts':
        return (
          <>
            <Button variant="outline" onClick={() => { setConflictDecisions({}); backToSelection() }}>
              返回
            </Button>
            <Button
              disabled={!uploadState.overwritePolicy}
              onClick={() => handleStartUpload()}
            >
              开始上传
            </Button>
          </>
        )
      case 'uploading':
        return (
          <Button variant="destructive" onClick={handleCancelUpload}>
            取消上传
          </Button>
        )
      case 'complete':
        return (
          <Button onClick={() => {
            handleDialogCancel()
            onComplete()
          }}>
            关闭
          </Button>
        )
      default:
        return null
    }
  }

  const handleDialogCancel = () => {
    close()
    setConflictDecisions({})
    onCancel()
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleDialogCancel()}>
      <DialogContent className="sm:max-w-200">
        <DialogHeader>
          <DialogTitle>上传文件和文件夹</DialogTitle>
        </DialogHeader>
        {renderContent()}
        <DialogFooter>
          {renderFooter()}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default MultiFileUploadDialog
