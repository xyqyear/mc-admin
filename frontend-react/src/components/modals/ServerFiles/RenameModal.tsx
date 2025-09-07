import React from 'react'
import { Modal, Form, Input } from 'antd'
import type { FormInstance } from 'antd'

interface RenameModalProps {
  open: boolean
  onCancel: () => void
  onOk: () => void
  form: FormInstance
  confirmLoading: boolean
}

const RenameModal: React.FC<RenameModalProps> = ({
  open,
  onCancel,
  onOk,
  form,
  confirmLoading
}) => {
  return (
    <Modal
      title="重命名"
      open={open}
      onOk={onOk}
      onCancel={onCancel}
      okText="确定"
      cancelText="取消"
      confirmLoading={confirmLoading}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="newName"
          label="新名称"
          rules={[
            { required: true, message: '请输入新名称' },
            { pattern: /^[^<>:"/\\|?*]+$/, message: '名称包含非法字符' }
          ]}
        >
          <Input placeholder="输入新名称" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

export default RenameModal