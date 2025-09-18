import { useEffect, useRef, useState } from 'react'

interface UsePageDragUploadOptions {
  onFileDrop?: (files: File[]) => void
  onError?: (message: string) => void
  accept?: string
  multiple?: boolean
}

export function usePageDragUpload(options: UsePageDragUploadOptions = {}) {
  const { onFileDrop, onError, accept, multiple = true } = options
  const [isDragging, setIsDragging] = useState(false)
  const dragCounterRef = useRef(0)

  useEffect(() => {
    const handleDragEnter = (e: DragEvent) => {
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

    const handleDragLeave = (e: DragEvent) => {
      e.preventDefault()
      e.stopPropagation()

      dragCounterRef.current--

      if (dragCounterRef.current === 0) {
        setIsDragging(false)
      }
    }

    const handleDragOver = (e: DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
    }

    const handleDrop = (e: DragEvent) => {
      e.preventDefault()
      e.stopPropagation()

      setIsDragging(false)
      dragCounterRef.current = 0

      const files = Array.from(e.dataTransfer?.files || [])

      if (files.length === 0) return

      // 检查是否包含文件夹
      const hasDirectories = files.some(file => file.size === 0 && file.type === '')
      if (hasDirectories && onError) {
        onError('仅支持上传文件，不支持文件夹')
        return
      }

      // 过滤文件类型
      let validFiles = files
      if (accept) {
        const acceptedTypes = accept.split(',').map(type => type.trim())
        validFiles = files.filter(file => {
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
        if (validFiles.length < files.length && onError) {
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

    // 绑定到整个页面
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
  }, [onFileDrop, accept, multiple, onError])

  return {
    isDragging
  }
}