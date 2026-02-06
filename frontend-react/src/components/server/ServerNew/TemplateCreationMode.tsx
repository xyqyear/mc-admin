import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Select, Button, Empty, Typography } from 'antd'
import { EyeOutlined } from '@ant-design/icons'
import { SimpleEditor } from '@/components/editors'
import RjsfForm from '@/components/forms/rjsfTheme'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema } from '@rjsf/utils'
import { useTemplates, useTemplateSchema } from '@/hooks/queries/base/useTemplateQueries'
import { useTemplateMutations } from '@/hooks/mutations/useTemplateMutations'

const { Text } = Typography

interface TemplateCreationModeProps {
  selectedTemplateId: number | null
  setSelectedTemplateId: (id: number | null) => void
  templateFormData: Record<string, unknown>
  setTemplateFormData: (data: Record<string, unknown>) => void
}

const TemplateCreationMode: React.FC<TemplateCreationModeProps> = ({
  selectedTemplateId,
  setSelectedTemplateId,
  templateFormData,
  setTemplateFormData,
}) => {
  const navigate = useNavigate()

  // Preview state (internal to this component)
  const [previewYaml, setPreviewYaml] = useState<string | null>(null)
  const [isPreviewModalVisible, setIsPreviewModalVisible] = useState(false)

  // Queries
  const { data: templates = [], isLoading: templatesLoading } = useTemplates()
  const { data: templateSchema, isLoading: schemaLoading } = useTemplateSchema(selectedTemplateId)

  // Mutations
  const { usePreviewRenderedYaml } = useTemplateMutations()
  const previewMutation = usePreviewRenderedYaml()

  const handleTemplateFormChange = (data: { formData?: Record<string, unknown> }) => {
    if (data.formData) {
      setTemplateFormData(data.formData)
    }
  }

  const handlePreviewYaml = async () => {
    if (!selectedTemplateId || !templateFormData) return

    const yaml = await previewMutation.mutateAsync({
      id: selectedTemplateId,
      variableValues: templateFormData,
    })
    setPreviewYaml(yaml)
    setIsPreviewModalVisible(true)
  }

  return (
    <div className="space-y-4">
      {/* Template Selection */}
      <Card title="选择模板" size="small">
        <Select
          placeholder="选择一个服务器模板"
          style={{ width: '100%' }}
          value={selectedTemplateId}
          onChange={setSelectedTemplateId}
          loading={templatesLoading}
          options={templates.map((t) => ({
            value: t.id,
            label: `${t.name}${t.description ? ` - ${t.description}` : ''}`,
          }))}
          notFoundContent={
            <Empty
              description="暂无模板"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Button type="link" onClick={() => navigate('/templates/new')}>
                创建模板
              </Button>
            </Empty>
          }
        />
      </Card>

      {/* Template Form */}
      {selectedTemplateId && templateSchema && (
        <Card
          title="配置参数"
          size="small"
          extra={
            <Button
              icon={<EyeOutlined />}
              onClick={handlePreviewYaml}
              loading={previewMutation.isPending}
            >
              预览 YAML
            </Button>
          }
        >
          {schemaLoading ? (
            <div className="text-center py-4">加载中...</div>
          ) : (
            <RjsfForm
              schema={templateSchema.json_schema as RJSFSchema}
              formData={templateFormData}
              validator={validator}
              onChange={handleTemplateFormChange}
              showErrorList={false}
              liveValidate
            >
              <div /> {/* Hide default submit button */}
            </RjsfForm>
          )}
        </Card>
      )}

      {/* Preview YAML Modal */}
      {previewYaml && (
        <div
          className={`fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 ${isPreviewModalVisible ? '' : 'hidden'}`}
          onClick={() => setIsPreviewModalVisible(false)}
        >
          <div
            className="bg-white rounded-lg p-4 w-3/4 max-h-[80vh] overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-4">
              <Text strong>预览生成的 YAML</Text>
              <Button onClick={() => setIsPreviewModalVisible(false)}>关闭</Button>
            </div>
            <SimpleEditor
              value={previewYaml}
              language="yaml"
              height="60vh"
              options={{ readOnly: true }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export default TemplateCreationMode
