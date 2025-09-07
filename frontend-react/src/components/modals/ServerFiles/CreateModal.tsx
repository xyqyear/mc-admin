import React from 'react'
import { Modal, Form, Input, Select } from 'antd'
import type { FormInstance } from 'antd'

const { Option } = Select

interface CreateModalProps {
  open: boolean
  onCancel: () => void
  onOk: () => void
  form: FormInstance
  confirmLoading: boolean
}

const CreateModal: React.FC<CreateModalProps> = ({
  open,
  onCancel,
  onOk,
  form,
  confirmLoading
}) => {
  return (
    <Modal
      title="新建文件/文件夹"
      open={open}
      onOk={onOk}
      onCancel={onCancel}
      okText="创建"
      cancelText="取消"
      confirmLoading={confirmLoading}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="fileType"
          label="类型"
          rules={[{ required: true, message: '请选择文件类型' }]}
          initialValue="file"
        >
          <Select>
            <Option value="file">文件</Option>
            <Option value="directory">文件夹</Option>
          </Select>
        </Form.Item>
        <Form.Item
          name="fileName"
          label="名称"
          rules={[
            { required: true, message: '请输入文件名' },
            { pattern: /^[^<>:"/\\|?*]+$/, message: '文件名包含非法字符' }
          ]}
        >
          <Input placeholder="输入文件名或文件夹名" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

export default CreateModal