import React from 'react'
import { Modal, Button, Result, Space, Divider } from 'antd'
import { DownloadOutlined, DatabaseOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

interface CompressionResultModalProps {
  open: boolean
  onCancel: () => void
  archiveFilename: string
  message: string
  onDownload: () => void
  downloadLoading: boolean
}

const CompressionResultModal: React.FC<CompressionResultModalProps> = ({
  open,
  onCancel,
  archiveFilename,
  message,
  onDownload,
  downloadLoading
}) => {
  const navigate = useNavigate()

  const handleNavigateToArchives = () => {
    onCancel()
    navigate('/archives')
  }

  return (
    <Modal
      title="压缩完成"
      open={open}
      onCancel={onCancel}
      footer={null}
      width={500}
      centered
    >
      <div className="space-y-4">
        <Result
          icon={<CheckCircleOutlined className="text-green-500" />}
          title="压缩包创建成功"
          subTitle={
            <div className="space-y-2">
              <div>{message}</div>
              <div className="font-mono text-sm bg-gray-50 p-2 rounded border">
                {archiveFilename}
              </div>
            </div>
          }
        />

        <Divider />

        <div className="text-center">
          <Space direction="vertical" size="middle" className="w-full">
            <div className="text-gray-600">
              选择下一步操作：
            </div>

            <Space size="middle">
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                onClick={onDownload}
                loading={downloadLoading}
                size="large"
              >
                立即下载
              </Button>

              <Button
                icon={<DatabaseOutlined />}
                onClick={handleNavigateToArchives}
                size="large"
              >
                压缩包管理
              </Button>
            </Space>

            <div className="text-gray-500 text-sm mt-4">
              压缩包已保存到系统中，您可以随时在压缩包管理界面找到它
            </div>
          </Space>
        </div>
      </div>
    </Modal>
  )
}

export default CompressionResultModal