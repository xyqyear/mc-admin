import React, { useState } from 'react'
import { useNavigate } from 'react-router'
import { Eye } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'

import { SimpleEditor } from '@/components/editors'
import RjsfForm from '@/components/forms/rjsfTheme'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema } from '@rjsf/utils'
import { useTemplates, useTemplateSchema } from '@/hooks/queries/base/useTemplateQueries'
import { useTemplateMutations } from '@/hooks/mutations/useTemplateMutations'

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

  const [previewYaml, setPreviewYaml] = useState<string | null>(null)
  const [isPreviewDialogOpen, setIsPreviewDialogOpen] = useState(false)

  const { data: templates = [], isLoading: templatesLoading } = useTemplates()
  const { data: templateSchema, isLoading: schemaLoading } = useTemplateSchema(selectedTemplateId)

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
    setIsPreviewDialogOpen(true)
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">选择模板</CardTitle>
        </CardHeader>
        <CardContent>
          <Select
            value={selectedTemplateId ? String(selectedTemplateId) : undefined}
            onValueChange={(v) => setSelectedTemplateId(Number(v))}
            itemToStringLabel={(v) => {
              const t = templates.find(t => String(t.id) === v)
              return t ? `${t.name}${t.description ? ` - ${t.description}` : ''}` : v
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="选择一个服务器模板" />
            </SelectTrigger>
            <SelectContent>
              {templatesLoading ? (
                <div className="flex justify-center py-4">
                  <Spinner className="size-4" />
                </div>
              ) : templates.length === 0 ? (
                <div className="text-center py-4 space-y-2">
                  <p className="text-sm text-muted-foreground">暂无模板</p>
                  <Button variant="link" size="sm" onClick={() => navigate('/templates/new')}>
                    创建模板
                  </Button>
                </div>
              ) : (
                templates.map((t) => (
                  <SelectItem key={t.id} value={String(t.id)}>
                    {t.name}{t.description ? ` - ${t.description}` : ''}
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {selectedTemplateId && templateSchema && (
        <Card>
          <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm">配置参数</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={handlePreviewYaml}
              disabled={previewMutation.isPending}
            >
              {previewMutation.isPending ? <Spinner className="mr-1 size-4" /> : <Eye className="mr-1 h-4 w-4" />}
              预览 YAML
            </Button>
          </CardHeader>
          <CardContent>
            {schemaLoading ? (
              <div className="text-center py-4 text-muted-foreground">加载中...</div>
            ) : (
              <RjsfForm
                schema={templateSchema.json_schema as RJSFSchema}
                formData={templateFormData}
                validator={validator}
                onChange={handleTemplateFormChange}
                showErrorList={false}
                liveValidate
              >
                <div />
              </RjsfForm>
            )}
          </CardContent>
        </Card>
      )}

      <Dialog open={isPreviewDialogOpen} onOpenChange={(o) => !o && setIsPreviewDialogOpen(false)}>
        <DialogContent className="sm:max-w-200">
          <DialogHeader>
            <DialogTitle>预览生成的 YAML</DialogTitle>
          </DialogHeader>
          {previewYaml && (
            <SimpleEditor
              value={previewYaml}
              language="yaml"
              height="60vh"
              options={{ readOnly: true }}
            />
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsPreviewDialogOpen(false)}>关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default TemplateCreationMode
