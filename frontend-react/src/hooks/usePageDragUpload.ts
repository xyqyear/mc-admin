import { useEffect, useRef, useState } from 'react'

interface UsePageDragUploadOptions {
  onFileDrop?: (files: File[]) => void
  onError?: (message: string) => void
  accept?: string
  multiple?: boolean
  allowDirectories?: boolean
}

export function usePageDragUpload(options: UsePageDragUploadOptions = {}) {
  const { onFileDrop, onError, accept, multiple = true, allowDirectories = false } = options
  const [isDragging, setIsDragging] = useState(false)
  const [isScanning, setIsScanning] = useState(false)
  const dragCounterRef = useRef(0)

  useEffect(() => {
    // 递归获取文件夹中的所有文件
    const getAllFilesFromDirectory = async (item: any): Promise<File[]> => {
      const files: File[] = []

      if (item.isFile) {
        return new Promise((resolve) => {
          item.file((originalFile: File) => {
            // 获取相对路径（移除前导斜杠）
            const relativePath = item.fullPath.substring(1)

            // 创建新的 File 对象，将 name 设置为完整路径
            const fileWithPath = new File([originalFile], relativePath, {
              type: originalFile.type,
              lastModified: originalFile.lastModified
            })

            resolve([fileWithPath])
          })
        })
      } else if (item.isDirectory) {
        const dirReader = item.createReader()
        return new Promise((resolve) => {
          const readEntries = async () => {
            const entries = await new Promise<any[]>((resolve) => {
              dirReader.readEntries(resolve)
            })

            if (entries.length === 0) {
              resolve(files)
              return
            }

            for (const entry of entries) {
              const entryFiles = await getAllFilesFromDirectory(entry)
              files.push(...entryFiles)
            }

            // 继续读取更多条目（Chrome限制每次只能读取100个）
            await readEntries()
          }

          readEntries().then(() => resolve(files))
        })
      }

      return files
    }
    const handleDragEnter = (evt: Event) => {
      const e = evt as DragEvent
      e.preventDefault()
      e.stopPropagation()

      dragCounterRef.current++

      if (e.dataTransfer?.items) {
        const hasFiles = Array.from(e.dataTransfer.items).some(
          item => item.kind === 'file'
        )
        if (hasFiles) {
          setIsDragging(true)
        }
      }
    }

    const handleDragLeave = (evt: Event) => {
      const e = evt as DragEvent
      e.preventDefault()
      e.stopPropagation()

      dragCounterRef.current--

      if (dragCounterRef.current === 0) {
        setIsDragging(false)
      }
    }

    const handleDragOver = (evt: Event) => {
      const e = evt as DragEvent
      e.preventDefault()
      e.stopPropagation()
    }

    const handleDrop = async (evt: Event) => {
      const e = evt as DragEvent
      e.preventDefault()
      e.stopPropagation()

      setIsDragging(false)
      dragCounterRef.current = 0

      let allFiles: File[] = []

      // 处理拖拽的项目（支持文件夹和文件的混合）
      if (e.dataTransfer?.items && allowDirectories) {
        setIsScanning(true)

        try {
          const items = e.dataTransfer.items;

          // 使用 Promise.all 并行处理所有项目
          const filePromises: Promise<File[]>[] = []

          for (let i = 0; i < items.length; i++) {
            const item = items[i]
            const entry = item.webkitGetAsEntry();
            if (entry) {
              // 将每个项目的处理添加到 Promise 数组
              filePromises.push(getAllFilesFromDirectory(entry))
            }
          }

          // 等待所有项目处理完成
          const fileArrays = await Promise.all(filePromises)

          // 合并所有文件
          fileArrays.forEach(files => {
            allFiles.push(...files)
          })
        } finally {
          setIsScanning(false)
        }

      } else {
        // 传统文件处理（不支持文件夹时）
        const files = Array.from(e.dataTransfer?.files || [])

        if (files.length === 0) return

        // 检查是否包含文件夹（只在不允许文件夹时检查）
        if (!allowDirectories) {
          const hasDirectories = files.some(file => file.size === 0 && file.type === '')
          if (hasDirectories && onError) {
            onError('仅支持上传文件，不支持文件夹')
            return
          }
        }

        allFiles = files
      }

      if (allFiles.length === 0) return

      // 过滤文件类型
      let validFiles = allFiles
      if (accept) {
        const acceptedTypes = accept.split(',').map(type => type.trim())
        validFiles = allFiles.filter(file => {
          return acceptedTypes.some(acceptedType => {
            if (acceptedType.startsWith('.')) {
              // 扩展名匹配
              return file.name.toLowerCase().endsWith(acceptedType.toLowerCase())
            } else if (acceptedType.includes('/')) {
              // MIME 类型匹配
              return file.type === acceptedType
            } else if (acceptedType.endsWith('/*')) {
              // 通配符匹配，如 image/*
              const mainType = acceptedType.split('/')[0]
              return file.type.startsWith(mainType + '/')
            }
            return false
          })
        })

        // 如果有不支持的文件格式
        if (validFiles.length < allFiles.length && onError) {
          if (accept === '.zip,.7z') {
            onError('仅支持7z或zip格式的压缩文件')
            return
          } else {
            onError(`仅支持以下格式的文件：${accept}`)
            return
          }
        }
      }

      // 如果不支持多文件，只取第一个
      if (!multiple && validFiles.length > 0) {
        validFiles = [validFiles[0]]
      }

      if (validFiles.length > 0 && onFileDrop) {
        onFileDrop(validFiles)
      }
    }

    // 绑定到document
    document.addEventListener('dragenter', handleDragEnter)
    document.addEventListener('dragleave', handleDragLeave)
    document.addEventListener('dragover', handleDragOver)
    document.addEventListener('drop', handleDrop)

    return () => {
      document.removeEventListener('dragenter', handleDragEnter)
      document.removeEventListener('dragleave', handleDragLeave)
      document.removeEventListener('dragover', handleDragOver)
      document.removeEventListener('drop', handleDrop)
    }
  }, [onFileDrop, accept, multiple, allowDirectories, onError])

  return {
    isDragging,
    isScanning
  }
}