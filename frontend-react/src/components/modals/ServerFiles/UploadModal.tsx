import React from 'react'
import { Modal, Upload, Button } from 'antd'
import { UploadOutlined } from '@ant-design/icons'

interface UploadModalProps {
  open: boolean
  onCancel: () => void
  onOk: () => void
  currentPath: string
  uploadFileList: any[]
  setUploadFileList: (fileList: any[]) => void
  confirmLoading: boolean
}

const UploadModal: React.FC<UploadModalProps> = ({
  open,
  onCancel,
  onOk,
  currentPath,
  uploadFileList,
  setUploadFileList,
  confirmLoading
}) => {
  const handleCancel = () => {
    onCancel()
    setUploadFileList([])
  }

  return (
    <Modal
      title="上传文件"
      open={open}
      onOk={onOk}
      onCancel={handleCancel}
      okText="上传"
      cancelText="取消"
      confirmLoading={confirmLoading}
    >
      <Upload
        fileList={uploadFileList}
        onChange={({ fileList }) => setUploadFileList(fileList)}
        beforeUpload={() => false} // Prevent automatic upload
        multiple
      >
        <Button icon={<UploadOutlined />}>选择文件</Button>
      </Upload>
      <div className="mt-2 text-gray-500">
        文件将上传到当前目录: {currentPath}
      </div>
    </Modal>
  )
}

export default UploadModal