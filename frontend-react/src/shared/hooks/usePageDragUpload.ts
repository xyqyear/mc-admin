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
    const getAllFilesFromDirectory = async (item: any): Promise<File[]> => {
      const files: File[] = []

      if (item.isFile) {
        return new Promise((resolve) => {
          item.file((originalFile: File) => {
            // Strip the leading "/" so the relative path can be used as the upload key.
            const relativePath = item.fullPath.substring(1)

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

            // Chrome's readEntries returns at most 100 entries per call; loop until empty.
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

      if (e.dataTransfer?.items && allowDirectories) {
        setIsScanning(true)

        try {
          const items = e.dataTransfer.items;

          const filePromises: Promise<File[]>[] = []

          for (let i = 0; i < items.length; i++) {
            const item = items[i]
            const entry = item.webkitGetAsEntry();
            if (entry) {
              filePromises.push(getAllFilesFromDirectory(entry))
            }
          }

          const fileArrays = await Promise.all(filePromises)

          fileArrays.forEach(files => {
            allFiles.push(...files)
          })
        } finally {
          setIsScanning(false)
        }

      } else {
        const files = Array.from(e.dataTransfer?.files || [])

        if (files.length === 0) return

        // Browsers expose dropped folders as zero-byte, empty-MIME entries; reject when only files are accepted.
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

      let validFiles = allFiles
      if (accept) {
        const acceptedTypes = accept.split(',').map(type => type.trim())
        validFiles = allFiles.filter(file => {
          return acceptedTypes.some(acceptedType => {
            if (acceptedType.startsWith('.')) {
              return file.name.toLowerCase().endsWith(acceptedType.toLowerCase())
            } else if (acceptedType.includes('/')) {
              return file.type === acceptedType
            } else if (acceptedType.endsWith('/*')) {
              const mainType = acceptedType.split('/')[0]
              return file.type.startsWith(mainType + '/')
            }
            return false
          })
        })

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

      if (!multiple && validFiles.length > 0) {
        validFiles = [validFiles[0]]
      }

      if (validFiles.length > 0 && onFileDrop) {
        onFileDrop(validFiles)
      }
    }

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