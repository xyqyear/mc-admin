import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { useEditorDraft } from '@/shared/hooks/useEditorDraft'
import { useFileContent } from '@/features/files/queries'
import { useFileMutations } from '@/features/files/commands'
import { detectFileLanguage, getComposeOverrideWarning, getLanguageEditorOptions, isFileEditable } from '@/features/files/editingConfig'
import type { FileItem } from '@/features/files/contracts'

export function useFileEditor(serverId: string | undefined) {
  const [editingFile, setEditingFile] = useState<FileItem | null>(null)
  const [isDiffDialogOpen, setIsDiffDialogOpen] = useState(false)
  const contentQuery = useFileContent(serverId, editingFile?.path ?? null)
  const { useUpdateFile } = useFileMutations(serverId)
  const updateFileMutation = useUpdateFile()
  const target = editingFile ? `${serverId}:${editingFile.path}` : null
  const currentTarget = useRef(target)
  currentTarget.current = target
  const editorDraft = useEditorDraft(target, editingFile ? contentQuery.data?.content : undefined)
  const getCurrentFileLanguageConfig = () => {
    if (!editingFile) return { language: 'text', options: {}, config: undefined, composeWarning: undefined }
    const config = detectFileLanguage(editingFile.name)
    const warning = getComposeOverrideWarning(editingFile.name)
    return { language: config.language, options: getLanguageEditorOptions(config.language), config, composeWarning: warning.shouldWarn ? warning : undefined }
  }
  const handleFileSave = async () => {
    if (!editingFile || !serverId || !editorDraft.ready || updateFileMutation.isPending) return
    try {
      await updateFileMutation.mutateAsync({ path: editingFile.path, content: editorDraft.draft ?? '' })
      if (currentTarget.current === target) setEditingFile(null)
    } catch { /* A rejected write leaves the session available for retry. */ }
  }
  return {
    editingFile, isEditDialogOpen: editingFile !== null, editorDraft, updateFileMutation,
    isDiffDialogOpen, setIsDiffDialogOpen,
    fileContent: editorDraft.draft ?? '', setFileContent: editorDraft.setDraft,
    originalFileContent: contentQuery.data?.content ?? '',
    isLoadingContent: contentQuery.isLoading, contentError: contentQuery.error, refetchContent: contentQuery.refetch,
    getCurrentFileLanguageConfig, handleFileSave,
    handleFileEdit: (file: FileItem) => {
      if (!isFileEditable(file.name)) { toast.warning('该文件不可编辑'); return }
      setEditingFile(file)
    },
    closeEditor: () => { if (!updateFileMutation.isPending) setEditingFile(null) },
    handleShowDiff: () => setIsDiffDialogOpen(true),
  }
}
