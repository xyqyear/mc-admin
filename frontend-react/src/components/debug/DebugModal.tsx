import React, { useState, useEffect, useCallback } from 'react'
import { Modal, Button, Form, Input, Space, Divider, Typography, Card, message } from 'antd'
import { BugOutlined, DeleteOutlined, SaveOutlined, ReloadOutlined } from '@ant-design/icons'
import { currentVersion } from '@/config/versionConfig'

const { Title, Text } = Typography

interface DebugModalProps {
  visible: boolean
  onClose: () => void
}

const VERSION_STORAGE_KEY = 'mc-admin-last-seen-version'
const REMIND_TIME_STORAGE_KEY = 'mc-admin-remind-time'

const DebugModal: React.FC<DebugModalProps> = ({ visible, onClose }) => {
  const [form] = Form.useForm()
  const [localStorageData, setLocalStorageData] = useState({
    version: '',
    remindTime: ''
  })

  // 读取当前 localStorage 数据
  const refreshData = useCallback(() => {
    const version = localStorage.getItem(VERSION_STORAGE_KEY) || ''
    const remindTime = localStorage.getItem(REMIND_TIME_STORAGE_KEY) || ''
    
    const data = { version, remindTime }
    setLocalStorageData(data)
    form.setFieldsValue(data)
  }, [form])

  useEffect(() => {
    if (visible) {
      refreshData()
    }
  }, [visible, refreshData])

  // 保存版本信息
  const handleSaveVersion = () => {
    const version = form.getFieldValue('version')
    if (version) {
      localStorage.setItem(VERSION_STORAGE_KEY, version)
      message.success(`版本已设置为: ${version}`)
      refreshData()
    }
  }

  // 保存提醒时间
  const handleSaveRemindTime = () => {
    const remindTime = form.getFieldValue('remindTime')
    if (remindTime) {
      try {
        // 验证日期格式
        const date = new Date(remindTime)
        if (isNaN(date.getTime())) {
          message.error('无效的日期格式，请使用 ISO 格式 (YYYY-MM-DDTHH:mm:ss.sssZ)')
          return
        }
        localStorage.setItem(REMIND_TIME_STORAGE_KEY, date.toISOString())
        message.success(`提醒时间已设置为: ${date.toLocaleString()}`)
        refreshData()
      } catch {
        message.error('无效的日期格式')
      }
    }
  }

  // 清空版本信息
  const handleClearVersion = () => {
    localStorage.removeItem(VERSION_STORAGE_KEY)
    message.success('版本信息已清空')
    refreshData()
  }

  // 清空提醒时间
  const handleClearRemindTime = () => {
    localStorage.removeItem(REMIND_TIME_STORAGE_KEY)
    message.success('提醒时间已清空')
    refreshData()
  }

  // 清空所有
  const handleClearAll = () => {
    localStorage.removeItem(VERSION_STORAGE_KEY)
    localStorage.removeItem(REMIND_TIME_STORAGE_KEY)
    message.success('所有调试数据已清空')
    refreshData()
  }

  // 设置为当前时间（稍后提醒测试）
  const handleSetCurrentTime = () => {
    const now = new Date().toISOString()
    form.setFieldValue('remindTime', now)
    localStorage.setItem(REMIND_TIME_STORAGE_KEY, now)
    message.success('已设置为当前时间')
    refreshData()
  }

  // 设置为一小时前（触发提醒测试）
  const handleSetOneHourAgo = () => {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString()
    form.setFieldValue('remindTime', oneHourAgo)
    localStorage.setItem(REMIND_TIME_STORAGE_KEY, oneHourAgo)
    message.success('已设置为一小时前，刷新页面将触发版本提醒')
    refreshData()
  }

  return (
    <Modal
      title={
        <Space>
          <BugOutlined className="text-orange-500" />
          <span>调试工具</span>
          <Text type="secondary" className="text-sm">
            (仅开发环境)
          </Text>
        </Space>
      }
      open={visible}
      onCancel={onClose}
      width={600}
      footer={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={refreshData}>
          刷新数据
        </Button>,
        <Button key="clear" danger icon={<DeleteOutlined />} onClick={handleClearAll}>
          清空所有
        </Button>,
        <Button key="close" type="primary" onClick={onClose}>
          关闭
        </Button>
      ]}
    >
      <div className="py-4">
        <Card size="small" className="mb-4">
          <Title level={5}>当前信息</Title>
          <div className="space-y-2">
            <div>
              <Text strong>当前版本: </Text>
              <Text code>{currentVersion}</Text>
            </div>
            <div>
              <Text strong>存储版本: </Text>
              <Text code>{localStorageData.version || '未设置'}</Text>
            </div>
            <div>
              <Text strong>提醒时间: </Text>
              <Text code>
                {localStorageData.remindTime 
                  ? new Date(localStorageData.remindTime).toLocaleString()
                  : '未设置'
                }
              </Text>
            </div>
          </div>
        </Card>

        <Form form={form} layout="vertical">
          <Divider>版本管理</Divider>
          
          <Form.Item
            label="设置存储版本"
            name="version"
            help="设置 localStorage 中存储的版本号，用于测试版本更新提醒"
          >
            <Space.Compact>
              <Input
                placeholder="例如: 1.0.0"
                style={{ width: 'calc(100% - 140px)' }}
              />
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSaveVersion}
                style={{ width: '70px' }}
              >
                保存
              </Button>
              <Button
                danger
                icon={<DeleteOutlined />}
                onClick={handleClearVersion}
                style={{ width: '70px' }}
              >
                清空
              </Button>
            </Space.Compact>
          </Form.Item>

          <Divider>提醒时间管理</Divider>

          <Form.Item
            label="设置提醒时间"
            name="remindTime"
            help="设置 localStorage 中的提醒时间 (ISO 格式)"
          >
            <Space.Compact>
              <Input
                placeholder="例如: 2024-01-01T12:00:00.000Z"
                style={{ width: 'calc(100% - 140px)' }}
              />
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSaveRemindTime}
                style={{ width: '70px' }}
              >
                保存
              </Button>
              <Button
                danger
                icon={<DeleteOutlined />}
                onClick={handleClearRemindTime}
                style={{ width: '70px' }}
              >
                清空
              </Button>
            </Space.Compact>
          </Form.Item>

          <div className="mb-4">
            <Text strong>快速设置：</Text>
            <div className="mt-2 space-x-2">
              <Button size="small" onClick={handleSetCurrentTime}>
                设为当前时间
              </Button>
              <Button size="small" type="primary" onClick={handleSetOneHourAgo}>
                设为一小时前（触发提醒）
              </Button>
            </div>
          </div>

          <Divider />

          <div className="text-sm text-gray-500">
            <Text type="secondary">
              <strong>使用说明：</strong>
            </Text>
            <ul className="mt-2 space-y-1 text-gray-500">
              <li>• 修改存储版本为较低版本（如 1.0.0），刷新页面测试版本更新提醒</li>
              <li>• 设置提醒时间为一小时前，刷新页面测试&quot;稍后提醒&quot;功能</li>
              <li>• 清空所有数据可重置为初始状态</li>
            </ul>
          </div>
        </Form>
      </div>
    </Modal>
  )
}

export default DebugModal