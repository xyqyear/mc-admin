import React from 'react'
import { UploadOutlined } from '@ant-design/icons'

interface DragDropOverlayProps {
  isDragging: boolean
}

const DragDropOverlay: React.FC<DragDropOverlayProps> = ({ isDragging }) => {
  if (!isDragging) return null

  return (
    <div className="fixed inset-0 bg-blue-500 bg-opacity-10 border-2 border-dashed border-blue-500 z-50 flex items-center justify-center">
      <div className="bg-white rounded-lg shadow-lg p-8 text-center">
        <UploadOutlined className="text-4xl text-blue-500 mb-4" />
        <div className="text-xl font-medium text-blue-600 mb-2">拖拽文件到此处上传</div>
        <div className="text-gray-500">松开鼠标完成文件选择</div>
      </div>
    </div>
  )
}

export default DragDropOverlay