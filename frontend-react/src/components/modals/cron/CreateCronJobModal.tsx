import React, { useState, useEffect } from 'react'
import { Plus, Pencil } from 'lucide-react'
import { Controller, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Spinner } from '@/components/ui/spinner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Field, FieldLabel, FieldError } from '@/components/ui/field'

import SchemaForm from '@/components/forms/SchemaForm'
import CronExpressionBuilder from '@/components/forms/CronExpressionBuilder'
import { useRegisteredCronJobs, useCronJob } from '@/hooks/queries/base/useCronQueries'
import { useCronMutations } from '@/hooks/mutations/useCronMutations'
import type { CreateCronJobRequest, UpdateCronJobRequest } from '@/hooks/api/cronApi'

const nameSchema = z.object({
  name: z
    .string()
    .min(1, '请输入任务名称')
    .max(100, '任务名称最多100个字符'),
})

type NameFormData = z.infer<typeof nameSchema>

interface CreateCronJobModalProps {
  open: boolean
  onCancel: () => void
  onSuccess?: () => void
  isEdit?: boolean
  cronjobId?: string
}

const CreateCronJobModal: React.FC<CreateCronJobModalProps> = ({
  open,
  onCancel,
  onSuccess,
  isEdit = false,
  cronjobId,
}) => {
  const [selectedJobType, setSelectedJobType] = useState<string | null>(null)
  const [jobParams, setJobParams] = useState<any>({})
  const [schemaFormKey, setSchemaFormKey] = useState(0)
  const [cronExpression, setCronExpression] = useState('0 0 * * *')
  const [secondField, setSecondField] = useState('')

  const form = useForm<NameFormData>({
    resolver: zodResolver(nameSchema),
    defaultValues: { name: '' },
  })

  const { data: registeredJobs, isLoading: jobsLoading } = useRegisteredCronJobs()
  const { data: cronJobData } = useCronJob(isEdit && cronjobId ? cronjobId : null)
  const { useCreateCronJob, useUpdateCronJob } = useCronMutations()
  const createMutation = useCreateCronJob()
  const updateMutation = useUpdateCronJob()

  useEffect(() => {
    if (open) {
      if (isEdit && cronJobData) {
        form.setValue('name', cronJobData.name)
        setSelectedJobType(cronJobData.identifier)
        setJobParams(cronJobData.params)
        setCronExpression(cronJobData.cron)
        setSecondField(cronJobData.second || '')
        setSchemaFormKey(prev => prev + 1)
      } else if (!isEdit) {
        form.reset()
        setSelectedJobType(null)
        setJobParams({})
        setSchemaFormKey(prev => prev + 1)
        setCronExpression('0 0 * * *')
        setSecondField('')
      }
    }
  }, [open, form, isEdit, cronJobData])

  const handleJobTypeChange = (value: string | null) => {
    if (!value) return
    setSelectedJobType(value)
    setJobParams({})
    setSchemaFormKey(prev => prev + 1)
  }

  const handleSubmit = async (values: NameFormData) => {
    if (!selectedJobType) return

    try {
      if (isEdit && cronjobId) {
        const updateRequest: UpdateCronJobRequest = {
          identifier: selectedJobType,
          params: jobParams,
          cron: cronExpression,
          second: secondField || undefined,
        }
        await updateMutation.mutateAsync({ cronjobId, request: updateRequest })
      } else {
        const createRequest: CreateCronJobRequest = {
          identifier: selectedJobType,
          params: jobParams,
          cron: cronExpression,
          name: values.name,
          second: secondField || undefined,
        }
        await createMutation.mutateAsync(createRequest)
      }

      form.reset()
      setSelectedJobType(null)
      setJobParams({})
      setCronExpression('0 0 * * *')
      setSecondField('')
      onCancel()
      onSuccess?.()
    } catch {
      // Error handled by mutation
    }
  }

  const selectedJobSchema = registeredJobs?.find(job => job.identifier === selectedJobType)
  const isPending = isEdit ? updateMutation.isPending : createMutation.isPending

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel() }}>
      <DialogContent className="sm:max-w-200 max-h-[85vh] overflow-y-auto" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isEdit ? <Pencil className="h-5 w-5" /> : <Plus className="h-5 w-5" />}
            {isEdit ? '编辑定时任务' : '创建定时任务'}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
          {/* Job Type Selection */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">选择任务类型</CardTitle>
            </CardHeader>
            <CardContent>
              <Select
                value={selectedJobType || undefined}
                onValueChange={handleJobTypeChange}
                disabled={isEdit || jobsLoading}
                itemToStringLabel={(v) => {
                  const job = registeredJobs?.find(j => j.identifier === v)
                  return job ? `${job.identifier} - ${job.description}` : String(v)
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="请选择任务类型" />
                </SelectTrigger>
                <SelectContent>
                  {registeredJobs?.map(job => (
                    <SelectItem key={job.identifier} value={job.identifier}>
                      <span className="font-medium">{job.identifier}</span>
                      <span className="text-xs text-muted-foreground ml-2">- {job.description}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </CardContent>
          </Card>

          {/* Restart-Backup Conflict Warning */}
          {selectedJobType === 'restart_server' && (
            <Alert>
              <AlertTitle>重启时间冲突提醒</AlertTitle>
              <AlertDescription>
                <p>为了避免数据丢失，请确保服务器重启时间不与备份任务时间重合。</p>
                <p className="mt-1"><strong>建议：</strong></p>
                <ul className="mt-1 ml-4 list-disc text-sm">
                  <li>如果配置了每15分钟备份（0,15,30,45分），请避开这些分钟进行重启</li>
                  <li>如果配置了每小时0分备份，请避开0分进行重启</li>
                  <li>建议在备份间隔的中间时间点进行重启，如40分、50分等</li>
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {/* Basic Configuration */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">基本配置</CardTitle>
            </CardHeader>
            <CardContent>
              <Field>
                <FieldLabel htmlFor="cron-name">任务名称</FieldLabel>
                <Controller
                  name="name"
                  control={form.control}
                  render={({ field, fieldState }) => (
                    <>
                      <Input
                        id="cron-name"
                        placeholder="为任务起一个描述性的名称"
                        disabled={isEdit}
                        {...field}
                      />
                      {fieldState.error && (
                        <FieldError>{fieldState.error.message}</FieldError>
                      )}
                    </>
                  )}
                />
              </Field>
            </CardContent>
          </Card>

          {/* Cron Expression Configuration */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">调度配置</CardTitle>
            </CardHeader>
            <CardContent>
              <CronExpressionBuilder
                cronValue={cronExpression}
                secondValue={secondField}
                onCronChange={setCronExpression}
                onSecondChange={setSecondField}
                disabled={isPending}
              />
            </CardContent>
          </Card>

          {/* Job Parameters */}
          {selectedJobSchema && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">任务参数</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground mb-4">
                  请根据任务类型配置相应的参数
                </p>
                <SchemaForm
                  key={schemaFormKey}
                  schema={selectedJobSchema.parameter_schema}
                  formData={jobParams}
                  onChange={setJobParams}
                  liveValidate="onChange"
                  showErrorList={false}
                />
              </CardContent>
            </Card>
          )}

          {!selectedJobType && (
            <Alert>
              <AlertTitle>请先选择任务类型</AlertTitle>
              <AlertDescription>
                选择任务类型后，系统将显示该类型任务的参数配置表单。
              </AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCancel}>
              取消
            </Button>
            <Button type="submit" disabled={!selectedJobType || isPending}>
              {isPending && <Spinner className="mr-2 size-4" />}
              {isEdit ? '更新任务' : '创建任务'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default CreateCronJobModal
