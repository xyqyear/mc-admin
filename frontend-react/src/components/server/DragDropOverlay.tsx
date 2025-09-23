import React from 'react'
import { UploadOutlined, LoadingOutlined, FileZipOutlined } from '@ant-design/icons'
import { Spin } from 'antd'

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

  // 根据不同页面类型配置不同的显示内容
  const getPageContent = () => {
    switch (pageType) {
      case 'archive':
        return {
          icon: <FileZipOutlined className="text-4xl text-blue-500 mb-4" />,
          title: '拖拽压缩包到此处上传',
          description: '支持 .zip 和 .7z 格式文件'
        }
      case 'serverFiles':
      default:
        return {
          icon: <UploadOutlined className="text-4xl text-blue-500 mb-4" />,
          title: allowDirectories ? '拖拽文件或文件夹到此处上传' : '拖拽文件到此处上传',
          description: '松开鼠标完成文件选择'
        }
    }
  }

  const pageContent = getPageContent()

  return (
    <div className="fixed inset-0 bg-blue-500 bg-opacity-10 border-2 border-dashed border-blue-500 z-50 flex items-center justify-center">
      <div className="bg-white rounded-lg shadow-lg p-8 text-center">
        {isScanning ? (
          <>
            <Spin
              indicator={<LoadingOutlined style={{ fontSize: 48 }} spin />}
              className="text-blue-500 mb-4"
            />
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