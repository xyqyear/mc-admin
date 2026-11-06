import { create } from 'zustand'
import { toast } from 'sonner'
import { useTaskCenterStore } from './panelStore'
import { animateUploadMinimize, clearUploadAnimations } from './minimize'

export type UploadStatus = 'select' | 'checking' | 'conflicts' | 'uploading' | 'retrying' | 'paused' | 'verifying' | 'complete' | 'error' | 'cancelled'
type UploadInput = { kind: 'files'; serverId: string; basePath: string; files: File[] } | { kind: 'archive'; basePath: string; files: File[] }
export type UploadTask = UploadInput & {
  id: string
  title: string
  status: UploadStatus
  started: boolean
  progress: number
  fileCount: number
  fileNames: string[]
  totalSize: number
  message: string
  detail?: string
  startTime: number
}

export function isUploadActive(task: UploadTask) {
  return task.started && !['complete', 'error', 'cancelled'].includes(task.status)
}

interface UploadState {
  tasks: UploadTask[]
  visibleId: string | null
}

export const useUploadStore = create<UploadState>(() => ({ tasks: [], visibleId: null }))
let uploadSequence = 0

function createUpload(input: UploadInput) {
  const id = `upload-${++uploadSequence}`
  const task: UploadTask = {
    ...input, files: [...input.files], id, title: input.files[0]?.name || '选择上传文件', status: 'select', started: false,
    progress: 0, message: '等待开始', fileCount: input.files.length, fileNames: input.files.map(file => file.name),
    totalSize: input.files.reduce((total, file) => total + file.size, 0), startTime: Date.now(),
  }
  useTaskCenterStore.getState().setOpen(false)
  useUploadStore.setState(state => ({ tasks: [...state.tasks.filter(item => item.started), task], visibleId: id }))
  return id
}

export function openFileUpload(serverId: string, basePath: string, files: File[] = []) {
  return createUpload({ kind: 'files', serverId, basePath, files })
}

export function openArchiveUpload(files: File[] = []) {
  return createUpload({ kind: 'archive', basePath: '/', files })
}

export function updateUpload(id: string, summary: Partial<Pick<UploadTask, 'title' | 'status' | 'progress' | 'message' | 'detail' | 'fileCount' | 'fileNames' | 'totalSize'>>) {
  useUploadStore.setState(state => ({ tasks: state.tasks.map(task => task.id === id
    ? { ...task, ...summary, started: task.started || (summary.status !== undefined && summary.status !== 'select') }
    : task) }))
}

export function reopenUpload(id: string) {
  if (!useUploadStore.getState().tasks.some(task => task.id === id)) return
  useTaskCenterStore.getState().setOpen(false)
  useUploadStore.setState({ visibleId: id })
}

export function hideUpload(id: string, element: HTMLElement | null) {
  const task = useUploadStore.getState().tasks.find(item => item.id === id)
  if (!task) return
  if (!task.started) {
    useUploadStore.setState(state => ({ tasks: state.tasks.filter(item => item.id !== id), visibleId: null }))
    return
  }
  animateUploadMinimize(element)
  useTaskCenterStore.getState().setActiveTab('upload')
  useTaskCenterStore.getState().setOpen(false)
  useUploadStore.setState({ visibleId: null })
  toast.info('上传窗口已收起，可在任务中心查看')
}

export function removeUpload(id: string) {
  useUploadStore.setState(state => ({
    tasks: state.tasks.filter(task => task.id !== id || isUploadActive(task)),
    visibleId: state.visibleId === id && !state.tasks.some(task => task.id === id && isUploadActive(task)) ? null : state.visibleId,
  }))
}

export function clearFinishedUploads() {
  for (const task of useUploadStore.getState().tasks) if (task.started && !isUploadActive(task)) removeUpload(task.id)
}

export function clearBrowserUploads() {
  clearUploadAnimations()
  useUploadStore.setState({ tasks: [], visibleId: null })
}
