import React from 'react'
import { Upload, FileArchive } from 'lucide-react'
import { Spinner } from '@/components/ui/spinner'

type DragDropPageType = 'serverFiles' | 'archive'

interface DragDropOverlayProps {
  isDragging: boolean
  isScanning?: boolean
  allowDirectories?: boolean
  pageType?: DragDropPageType
}

const DragDropOverlay: React.FC<DragDropOverlayProps> = ({
  isDragging,
  isScanning = false,
  allowDirectories = false,
  pageType = 'serverFiles'
}) => {
  if (!isDragging && !isScanning) return null

  const getPageContent = () => {
    switch (pageType) {
      case 'archive':
        return {
          icon: <FileArchive className="h-10 w-10 text-blue-500 mb-4" />,
          title: '拖拽压缩包到此处上传',
          description: '支持 .zip 和 .7z 格式文件'
        }
      case 'serverFiles':
      default:
        return {
          icon: <Upload className="h-10 w-10 text-blue-500 mb-4" />,
          title: allowDirectories ? '拖拽文件或文件夹到此处上传' : '拖拽文件到此处上传',
          description: '松开鼠标完成文件选择'
        }
    }
  }

  const pageContent = getPageContent()

  return (
    <div className="fixed inset-0 bg-blue-500/10 border-2 border-dashed border-blue-500 z-50 flex items-center justify-center">
      <div className="bg-white rounded-lg shadow-lg p-8 text-center">
        {isScanning ? (
          <>
            <Spinner className="size-12 text-blue-500 mb-4" />
            <div className="text-xl font-medium text-blue-600 mb-2">
              正在扫描文件...
            </div>
            <div className="text-gray-500">请稍候，正在处理文件和文件夹</div>
          </>
        ) : (
          <>
            {pageContent.icon}
            <div className="text-xl font-medium text-blue-600 mb-2">
              {pageContent.title}
            </div>
            <div className="text-gray-500">{pageContent.description}</div>
          </>
        )}
      </div>
    </div>
  )
}

export default DragDropOverlay
