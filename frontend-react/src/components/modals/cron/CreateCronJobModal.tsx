import React, { useState, useEffect } from 'react'
import {
  Modal,
  Form,
  Input,
  Select,
  Button,
  Alert,
  Typography,
  Card
} from 'antd'
import { PlusOutlined, InfoCircleOutlined, EditOutlined } from '@ant-design/icons'
import SchemaForm from '@/components/forms/SchemaForm'
import CronExpressionBuilder from '@/components/forms/CronExpressionBuilder'
import { useRegisteredCronJobs, useCronJob } from '@/hooks/queries/base/useCronQueries'
import { useCronMutations } from '@/hooks/mutations/useCronMutations'
import type { CreateCronJobRequest, UpdateCronJobRequest } from '@/hooks/api/cronApi'

const { Text } = Typography

interface CreateCronJobModalProps {
  open: boolean
  onCancel: () => void
  onSuccess?: () => void
  // Edit mode props
  isEdit?: boolean
  cronjobId?: string
}

const CreateCronJobModal: React.FC<CreateCronJobModalProps> = ({
  open,
  onCancel,
  onSuccess,
  isEdit = false,
  cronjobId
}) => {
  const [form] = Form.useForm()
  const [selectedJobType, setSelectedJobType] = useState<string | null>(null)
  const [jobParams, setJobParams] = useState<any>({})
  const [schemaFormKey, setSchemaFormKey] = useState(0)
  const [cronExpression, setCronExpression] = useState('0 0 * * *')
  const [secondField, setSecondField] = useState('')

  const { data: registeredJobs, isLoading: jobsLoading } = useRegisteredCronJobs()
  const { data: cronJobData } = useCronJob(isEdit && cronjobId ? cronjobId : null)
  const { useCreateCronJob, useUpdateCronJob } = useCronMutations()
  const createMutation = useCreateCronJob()
  const updateMutation = useUpdateCronJob()

  // Reset form when modal opens/closes or populate with existing data in edit mode
  useEffect(() => {
    if (open) {
      if (isEdit && cronJobData) {
        // Populate form with existing data in edit mode
        form.setFieldsValue({
          name: cronJobData.name
        })
        setSelectedJobType(cronJobData.identifier)
        setJobParams(cronJobData.params)
        setCronExpression(cronJobData.cron)
        setSecondField(cronJobData.second || '')
        setSchemaFormKey(prev => prev + 1)
      } else {
        // Reset form for create mode
        form.resetFields()
        setSelectedJobType(null)
        setJobParams({})
        setSchemaFormKey(prev => prev + 1)
        setCronExpression('0 0 * * *')
        setSecondField('')
      }
    }
  }, [open, form, isEdit, cronJobData])

  const handleJobTypeChange = (value: string) => {
    setSelectedJobType(value)
    setJobParams({})
    setSchemaFormKey(prev => prev + 1)
  }

  const handleParamsChange = (data: any) => {
    setJobParams(data)
  }

  const handleSubmit = async () => {
    try {
      const formValues = await form.validateFields()

      if (!selectedJobType) {
        return
      }

      if (isEdit && cronjobId) {
        // Update existing cron job
        const updateRequest: UpdateCronJobRequest = {
          identifier: selectedJobType,
          params: jobParams,
          cron: cronExpression,
          second: secondField || undefined
        }

        await updateMutation.mutateAsync({ cronjobId, request: updateRequest })
      } else {
        // Create new cron job
        const createRequest: CreateCronJobRequest = {
          identifier: selectedJobType,
          params: jobParams,
          cron: cronExpression,
          name: formValues.name,
          second: secondField || undefined
        }

        await createMutation.mutateAsync(createRequest)
      }

      // Reset form and close modal
      form.resetFields()
      setSelectedJobType(null)
      setJobParams({})
      setCronExpression('0 0 * * *')
      setSecondField('')
      onCancel()

      if (onSuccess) {
        onSuccess()
      }
    } catch (error) {
      // Error is handled by the mutation
      console.error(`${isEdit ? 'Update' : 'Create'} cron job failed:`, error)
    }
  }

  const selectedJobSchema = registeredJobs?.find(job => job.identifier === selectedJobType)

  return (
    <Modal
      title={
        <div className="flex items-center gap-2">
          {isEdit ? <EditOutlined /> : <PlusOutlined />}
          <span>{isEdit ? '编辑定时任务' : '创建定时任务'}</span>
        </div>
      }
      open={open}
      onCancel={onCancel}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          取消
        </Button>,
        <Button
          key="submit"
          type="primary"
          loading={isEdit ? updateMutation.isPending : createMutation.isPending}
          onClick={handleSubmit}
          disabled={!selectedJobType}
        >
          {isEdit ? '更新任务' : '创建任务'}
        </Button>
      ]}
      width={800}
      destroyOnHidden
      styles={{
        body: {
          maxHeight: 'calc(100vh - 300px)',
          overflowY: 'auto'
        }
      }}
    >
      <div className="space-y-6">
        {/* Job Type Selection */}
        <Card size="small" title="选择任务类型">
          <Select
            placeholder="请选择任务类型"
            style={{ width: '100%' }}
            loading={jobsLoading}
            value={selectedJobType}
            onChange={handleJobTypeChange}
            disabled={isEdit}
            options={registeredJobs?.map(job => ({
              label: (
                <div className="flex items-center space-x-2">
                  <span className="font-medium">{job.identifier}</span>
                  <span className="text-xs text-gray-500">- {job.description}</span>
                </div>
              ),
              value: job.identifier
            }))}
          />
        </Card>

        {/* Restart-Backup Conflict Warning */}
        {selectedJobType === 'restart_server' && (
          <Alert
            type="warning"
            showIcon
            title="重启时间冲突提醒"
            description={
              <div>
                <p>为了避免数据丢失，请确保服务器重启时间不与备份任务时间重合。</p>
                <p><strong>建议：</strong></p>
                <ul className="mt-2 ml-4">
                  <li>如果配置了每15分钟备份（0,15,30,45分），请避开这些分钟进行重启</li>
                  <li>如果配置了每小时0分备份，请避开0分进行重启</li>
                  <li>建议在备份间隔的中间时间点进行重启，如40分、50分等</li>
                </ul>
              </div>
            }
            className="mb-4"
          />
        )}

        {/* Basic Configuration */}
        <Card size="small" title="基本配置">
          <Form
            form={form}
            layout="vertical"
            initialValues={{
              name: ''
            }}
          >
            <Form.Item
              label="任务名称"
              name="name"
              rules={[
                { required: true, message: '请输入任务名称' },
                { max: 100, message: '任务名称最多100个字符' }
              ]}
            >
              <Input
                placeholder="为任务起一个描述性的名称"
                disabled={isEdit}
              />
            </Form.Item>
          </Form>
        </Card>

        {/* Cron Expression Configuration */}
        <Card size="small" title="调度配置">
          <CronExpressionBuilder
            cronValue={cronExpression}
            secondValue={secondField}
            onCronChange={setCronExpression}
            onSecondChange={setSecondField}
            disabled={createMutation.isPending}
          />
        </Card>

        {/* Job Parameters */}
        {selectedJobSchema && (
          <Card size="small" title="任务参数">
            <div className="mb-4">
              <Text type="secondary" className="text-sm">
                请根据任务类型配置相应的参数
              </Text>
            </div>

            <SchemaForm
              key={schemaFormKey}
              schema={selectedJobSchema.parameter_schema}
              formData={jobParams}
              onChange={handleParamsChange}
              liveValidate="onChange"
              showErrorList={false}
            />
          </Card>
        )}

        {!selectedJobType && (
          <Alert
            title="请先选择任务类型"
            description="选择任务类型后，系统将显示该类型任务的参数配置表单。"
            type="info"
            showIcon
            icon={<InfoCircleOutlined />}
          />
        )}
      </div>
    </Modal>
  )
}

export default CreateCronJobModal