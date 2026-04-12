import React, { useState, useMemo } from 'react'
import { toast } from 'sonner'
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

import type {
  OverwriteConflict,
  OverwritePolicy,
  FileStructureItem
} from '@/hooks/api/fileApi'
import { useFileMutations } from '@/hooks/mutations/useFileMutations'
import FileUploadTree from './FileUploadTree'
import ConflictTree from './ConflictTree'

interface MultiFileUploadModalProps {
  open: boolean
  onCancel: () => void
  onComplete: () => void
  serverId: string
  basePath: string
  initialFiles?: File[]
}

interface UploadStep {
  step: 'select' | 'conflicts' | 'uploading' | 'complete'
  files: File[]
  conflicts: OverwriteConflict[]
  sessionId?: string
  overwritePolicy?: OverwritePolicy
  uploadProgress?: {
    totalProgress: number
    uploadedFiles: number
    totalFiles: number
    totalSize: number
    uploadedSize: number
  }
  results?: Record<string, { status: string; reason?: string }>
  error?: string
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const MultiFileUploadModal: React.FC<MultiFileUploadModalProps> = ({
  open,
  onCancel,
  onComplete,
  serverId,
  basePath,
  initialFiles = []
}) => {
  const {
    useCheckUploadConflicts,
    useSetUploadPolicy,
    useUploadMultipleFiles
  } = useFileMutations(serverId)

  const checkConflictsMutation = useCheckUploadConflicts()
  const setUploadPolicyMutation = useSetUploadPolicy()
  const uploadMultipleFilesMutation = useUploadMultipleFiles()

  const [uploadState, setUploadState] = useState<UploadStep>({
    step: 'select',
    files: [],
    conflicts: []
  })

  const [conflictDecisions, setConflictDecisions] = useState<Record<string, boolean>>({})
  const [uploadAbortController, setUploadAbortController] = useState<AbortController | null>(null)

  const resetState = () => {
    setUploadState({
      step: 'select',
      files: [],
      conflicts: [],
      sessionId: undefined,
      overwritePolicy: undefined,
      uploadProgress: undefined,
      results: undefined,
      error: undefined
    })
    setConflictDecisions({})
    setUploadAbortController(null)
  }

  React.useEffect(() => {
    if (open && initialFiles.length > 0) {
      resetState()
      setUploadState({
        step: 'select',
        files: initialFiles,
        conflicts: [],
        sessionId: undefined,
        overwritePolicy: undefined,
        uploadProgress: undefined,
        results: undefined,
        error: undefined
      })
    } else if (open) {
      resetState()
    } else if (!open) {
      resetState()
    }
  }, [open, initialFiles])

  const buildFileStructure = (files: File[]): FileStructureItem[] => {
    const structure: FileStructureItem[] = []
    const directories = new Set<string>()

    files.forEach(file => {
      const relativePath = (file as any).webkitRelativePath || file.name
      const pathParts = relativePath.split('/')
      let currentPath = ''

      for (let i = 0; i < pathParts.length - 1; i++) {
        currentPath += (currentPath ? '/' : '') + pathParts[i]
        if (!directories.has(currentPath)) {
          directories.add(currentPath)
          structure.push({
            path: currentPath,
            name: pathParts[i],
            type: 'directory'
          })
        }
      }

      structure.push({
        path: relativePath,
        name: file.name,
        type: 'file',
        size: file.size
      })
    })

    return structure
  }

  const totalSize = useMemo(() => {
    return uploadState.files.reduce((total, file) => total + file.size, 0)
  }, [uploadState.files])

  const handleCheckConflicts = async () => {
    const fileStructure = buildFileStructure(uploadState.files)

    try {
      const response = await checkConflictsMutation.mutateAsync({
        path: basePath,
        uploadRequest: { files: fileStructure }
      })

      setUploadState(prev => ({
        ...prev,
        step: response.conflicts.length > 0 ? 'conflicts' : 'uploading',
        conflicts: response.conflicts,
        sessionId: response.session_id
      }))

      if (response.conflicts.length > 0) {
        const defaultDecisions: Record<string, boolean> = {}
        response.conflicts.forEach(conflict => {
          defaultDecisions[conflict.path] = true
        })
        setConflictDecisions(defaultDecisions)
      }

      if (response.conflicts.length === 0) {
        await handleStartUpload(response.session_id, { mode: 'always_overwrite' })
      }
    } catch {
      toast.error('检查冲突失败')
    }
  }

  const handleOverwritePolicy = (policy: OverwritePolicy) => {
    setUploadState(prev => ({ ...prev, overwritePolicy: policy }))
  }

  const handleStartUpload = async (sessionId?: string, policy?: OverwritePolicy) => {
    const currentSessionId = sessionId || uploadState.sessionId
    const currentPolicy = policy || uploadState.overwritePolicy

    if (!currentSessionId || !currentPolicy) {
      toast.error('缺少上传会话或策略')
      return
    }

    setUploadState(prev => ({
      ...prev,
      step: 'uploading',
      uploadProgress: {
        totalProgress: 0,
        uploadedFiles: 0,
        totalFiles: prev.files.length,
        totalSize,
        uploadedSize: 0
      }
    }))

    try {
      const needsChunking = uploadState.files.length > 1000
      const abortController = new AbortController()
      setUploadAbortController(abortController)

      await setUploadPolicyMutation.mutateAsync({
        sessionId: currentSessionId,
        policy: currentPolicy,
        reusable: needsChunking
      })

      const result = await uploadMultipleFilesMutation.mutateAsync({
        sessionId: currentSessionId,
        path: basePath,
        files: uploadState.files,
        abortSignal: abortController.signal,
        onProgress: (progress) => {
          setUploadState(prev => ({
            ...prev,
            uploadProgress: {
              ...prev.uploadProgress!,
              totalProgress: progress.percent,
              uploadedSize: progress.loaded
            }
          }))
        }
      })

      setUploadState(prev => ({
        ...prev,
        step: 'complete',
        results: result.results
      }))
    } catch (error: any) {
      if (error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
        toast.info('上传已取消')
        setUploadState(prev => ({
          ...prev,
          step: 'select',
          error: '上传已取消'
        }))
      } else {
        toast.error('上传失败')
        setUploadState(prev => ({
          ...prev,
          step: 'select',
          error: error.message || '上传失败'
        }))
      }
    } finally {
      setUploadAbortController(null)
    }
  }

  const handleCancelUpload = () => {
    if (uploadAbortController) {
      uploadAbortController.abort()
      toast.info('正在取消上传...')
    }
  }

  const handleUploadSuccess = () => {
    onComplete()
    setUploadState({ step: 'select', files: [], conflicts: [] })
    setConflictDecisions({})
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
                          overwrite: conflictDecisions[c.path] ?? false
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
              {uploadState.files.length > 1000 && (
                <p className="text-sm text-muted-foreground">
                  分块上传模式 - 每批次最多1000个文件
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
      case 'select':
        return (
          <>
            <Button variant="outline" onClick={onCancel}>取消</Button>
            <Button
              disabled={uploadState.files.length === 0}
              onClick={handleCheckConflicts}
            >
              {checkConflictsMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              检查冲突并上传
            </Button>
          </>
        )
      case 'conflicts':
        return (
          <>
            <Button variant="outline" onClick={() => setUploadState(prev => ({ ...prev, step: 'select' }))}>
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
            resetState()
            onCancel()
            handleUploadSuccess()
          }}>
            关闭
          </Button>
        )
      default:
        return null
    }
  }

  const handleModalCancel = () => {
    if (uploadState.step === 'uploading' && uploadAbortController) {
      handleCancelUpload()
    }
    onCancel()
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleModalCancel()}>
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

export default MultiFileUploadModal
