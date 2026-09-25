import React, { useEffect, useState, useMemo, useRef } from "react"
import { useNavigate, useParams, useSearchParams } from 'react-router'
import { toast } from "sonner"
import { Save, ArrowLeft, FileText, GitCompare } from "lucide-react"

import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { Textarea } from "@/shared/ui/textarea"
import { Field, FieldError, FieldLabel } from "@/shared/ui/field"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Alert, AlertTitle, AlertDescription } from "@/shared/ui/alert"
import { Spinner } from "@/shared/ui/spinner"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/shared/ui/tabs"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/shared/ui/dialog"

import PageHeader from "@/shared/layout/PageHeader"
import LoadingSpinner from "@/shared/layout/LoadingSpinner"
import { ComposeYamlEditor, MonacoDiffEditor } from "@/shared/editors/index"
import {
  VariableDefinitionForm,
  convertToFormData,
  convertToApiFormat,
  type VariableFormData,
} from "@/features/templates/ui/index"
import {
  useTemplate,
  useDefaultVariables,
} from "@/features/templates/queries"
import { useTemplateMutations } from "@/features/templates/commands"
import { useEditorDraft } from '@/shared/hooks/useEditorDraft'
import type { VariableDefinition, TemplateCreateRequest, TemplateUpdateRequest } from '@/features/templates/contracts';

const extractVariablesFromYaml = (yaml: string): string[] => {
  const pattern = /\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g
  const matches = yaml.matchAll(pattern)
  return [...new Set([...matches].map((m) => m[1]))]
}

const TemplateEdit: React.FC = () => {
  const navigate = useNavigate()
  const { id } = useParams<{ id: string }>()
  const [searchParams] = useSearchParams()
  const copyFromId = searchParams.get("copyFrom")

  const isEditMode = !!id
  const templateId = id ? parseInt(id, 10) : copyFromId ? parseInt(copyFromId, 10) : null
  const isNewTemplate = !isEditMode && !copyFromId

  const [nameError, setNameError] = useState("")
  const [isCompareVisible, setIsCompareVisible] = useState(false)
  const [diffTab, setDiffTab] = useState("yaml")

  const originalYamlRef = useRef<string>("")
  const originalVariablesRef = useRef<VariableDefinition[]>([])

  const { data: template, isLoading, error: templateError, refetch: refetchTemplate } = useTemplate(templateId)
  const { data: defaultVariablesData, isLoading: isLoadingDefaults, error: defaultsError, refetch: refetchDefaults } = useDefaultVariables()
  const remoteDraft = useMemo(() => {
    if (template) return {
      name: isEditMode ? template.name : '', description: template.description ?? '',
      yamlContent: template.yaml_template, variables: convertToFormData(template.variable_definitions),
    }
    if (isNewTemplate && defaultVariablesData) return {
      name: '', description: '', yamlContent: '', variables: convertToFormData(defaultVariablesData.variable_definitions),
    }
  }, [template, isEditMode, isNewTemplate, defaultVariablesData])
  const editor = useEditorDraft(`${id ?? 'new'}:${copyFromId ?? ''}`, remoteDraft)
  const form = editor.draft ?? { name: '', description: '', yamlContent: '', variables: [] }
  const { name, description, yamlContent, variables } = form
  const setName = (name: string) => editor.setDraft({ ...form, name })
  const setDescription = (description: string) => editor.setDraft({ ...form, description })
  const setYamlContent = (yamlContent: string) => editor.setDraft({ ...form, yamlContent })
  const setVariables = (variables: VariableFormData[]) => editor.setDraft({ ...form, variables })

  const { useCreateTemplate, useUpdateTemplate } = useTemplateMutations()
  const createMutation = useCreateTemplate()
  const updateMutation = useUpdateTemplate()

  useEffect(() => {
    if (template && isEditMode) {
      originalYamlRef.current = template.yaml_template
      originalVariablesRef.current = template.variable_definitions
    }
  }, [template, isEditMode])

  const yamlVariables = useMemo(
    () => extractVariablesFromYaml(yamlContent),
    [yamlContent]
  )

  const validationErrors = useMemo(() => {
    const errors: string[] = []
    const definedVars = new Set(variables.map((v) => v.name).filter(Boolean))

    const undefinedVars = yamlVariables.filter((v) => !definedVars.has(v))
    if (undefinedVars.length > 0) {
      errors.push(`YAML 中使用了未定义的变量: ${undefinedVars.join(", ")}`)
    }

    const unusedVars = [...definedVars].filter((v) => !yamlVariables.includes(v))
    if (unusedVars.length > 0) {
      errors.push(`已定义但未在 YAML 中使用的变量: ${unusedVars.join(", ")}`)
    }

    const varNames = variables.map((v) => v.name).filter(Boolean)
    const duplicates = varNames.filter((n, i) => varNames.indexOf(n) !== i)
    if (duplicates.length > 0) {
      errors.push(`变量名重复: ${[...new Set(duplicates)].join(", ")}`)
    }

    return errors
  }, [yamlVariables, variables])

  const handleVariablesChange = (newVariables: VariableFormData[]) => {
    setVariables(newVariables)
  }

  const handleCompare = async () => {
    if (!isEditMode) return
    try {
      const result = await refetchTemplate({ throwOnError: true })
      if (result.data) {
        originalYamlRef.current = result.data.yaml_template
        originalVariablesRef.current = result.data.variable_definitions
      }
      setIsCompareVisible(true)
    } catch {
      toast.warning("获取最新配置失败，使用当前缓存的配置进行对比")
      setIsCompareVisible(true)
    }
  }

  const currentApiVariables = convertToApiFormat(variables)

  const validateForm = (): boolean => {
    if (!name.trim()) {
      setNameError("请输入模板名称")
      return false
    }
    if (name.length > 100) {
      setNameError("模板名称最长 100 个字符")
      return false
    }
    setNameError("")
    return true
  }

  const handleSave = async () => {
    if (!editor.ready) return
    if (!validateForm()) return

    if (!yamlContent.trim()) {
      toast.error("请输入 YAML 模板内容")
      return
    }

    if (validationErrors.length > 0) {
      toast.error("请先修复验证错误")
      return
    }

    const apiVariables = convertToApiFormat(variables)

    try {
      if (isEditMode && id) {
        const request: TemplateUpdateRequest = {
          name,
          description: description || undefined,
          yaml_template: yamlContent,
          variable_definitions: apiVariables,
        }
        await updateMutation.mutateAsync({ id: parseInt(id, 10), request })
        navigate("/templates")
      } else {
        const request: TemplateCreateRequest = {
          name,
          description: description || undefined,
          yaml_template: yamlContent,
          variable_definitions: apiVariables,
        }
        await createMutation.mutateAsync(request)
        navigate("/templates")
      }
    } catch {
      // The mutation reports the error; the form remains available for retry.
    }
  }

  if ((isLoading && templateId) || (isNewTemplate && isLoadingDefaults)) {
    return <LoadingSpinner />
  }

  if (!editor.ready) {
    return <Alert variant="destructive"><AlertTitle>加载模板失败</AlertTitle>
      <AlertDescription>{templateError?.message || defaultsError?.message || '模板内容尚不可用'}
        <Button onClick={() => { void (isNewTemplate ? refetchDefaults() : refetchTemplate()) }}>重试</Button>
      </AlertDescription>
    </Alert>
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={isEditMode ? "编辑模板" : copyFromId ? "复制模板" : "新建模板"}
        icon={<FileText className="h-5 w-5" />}
      />

      <Card>
        <CardHeader>
          <CardTitle>基本信息</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field data-invalid={!!nameError || undefined}>
            <FieldLabel htmlFor="template-name">模板名称</FieldLabel>
            <Input
              id="template-name"
              placeholder="例如: paper-server"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (nameError) setNameError("")
              }}
              aria-invalid={!!nameError || undefined}
            />
            {nameError && <FieldError>{nameError}</FieldError>}
          </Field>
          <Field>
            <FieldLabel htmlFor="template-description">描述</FieldLabel>
            <Textarea
              id="template-description"
              placeholder="模板描述（可选）"
              rows={2}
              maxLength={500}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>YAML 模板</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <AlertTitle>使用 {'{变量名}'} 格式定义占位符</AlertTitle>
            <AlertDescription>
              当前 YAML 中使用的变量：{yamlVariables.length > 0 ? yamlVariables.join(", ") : "无"}
            </AlertDescription>
          </Alert>
          <Alert>
            <AlertTitle>固定容器内游戏端口</AlertTitle>
            <AlertDescription>
              保存模板时必须显式设置 SERVER_PORT=25565，ports 中的容器内 TCP 游戏端口也必须固定为 25565。宿主机端口可使用变量。OVERRIDE_SERVER_PROPERTIES 请省略或固定为 true，SKIP_SERVER_PROPERTIES 请省略或固定为 false。
            </AlertDescription>
          </Alert>

          <ComposeYamlEditor
            value={yamlContent}
            onChange={(value) => setYamlContent(value || "")}
            autoHeight
            minHeight={400}
            path="template.yml"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>变量定义 ({variables.length})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <AlertTitle>定义模板变量</AlertTitle>
            <AlertDescription>在此定义模板中使用的所有变量。YAML 中的变量必须与此处定义的变量一一对应。</AlertDescription>
          </Alert>

          <VariableDefinitionForm
            value={variables}
            onChange={handleVariablesChange}
            title="自定义变量列表"
          />
        </CardContent>
      </Card>

      {validationErrors.length > 0 && (
        <Alert variant="destructive">
          <AlertTitle>验证错误</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4">
              {validationErrors.map((error, index) => (
                <li key={index}>{error}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardContent className="flex justify-between pt-6">
          <Button variant="outline" onClick={() => navigate(-1)}>
            <ArrowLeft className="mr-1 h-4 w-4" />
            返回
          </Button>
          <div className="flex items-center gap-2">
            {isEditMode && (
              <Button variant="outline" onClick={handleCompare}>
                <GitCompare className="mr-1 h-4 w-4" />
                差异对比
              </Button>
            )}
            <Button
              onClick={handleSave}
              disabled={createMutation.isPending || updateMutation.isPending || validationErrors.length > 0}
            >
              {(createMutation.isPending || updateMutation.isPending) && <Spinner className="mr-2 size-4" />}
              <Save className="mr-1 h-4 w-4" />
              {isEditMode ? "保存" : "创建"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Dialog open={isCompareVisible} onOpenChange={(o) => !o && setIsCompareVisible(false)}>
        <DialogContent className="sm:max-w-350">
          <DialogHeader>
            <DialogTitle>模板差异对比</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Alert>
              <AlertTitle>差异对比视图</AlertTitle>
              <AlertDescription>左侧为服务器当前配置，右侧为本地编辑的配置。高亮显示的是差异部分。</AlertDescription>
            </Alert>
            <Tabs value={diffTab} onValueChange={setDiffTab}>
              <TabsList>
                <TabsTrigger value="yaml">YAML 模板</TabsTrigger>
                <TabsTrigger value="variables">变量定义</TabsTrigger>
              </TabsList>
              <TabsContent value="yaml">
                <div className="border rounded-md overflow-hidden h-125">
                  <MonacoDiffEditor
                    height="500px"
                    language="yaml"
                    original={originalYamlRef.current}
                    modified={yamlContent}
                  />
                </div>
              </TabsContent>
              <TabsContent value="variables">
                <div className="border rounded-md overflow-hidden h-125">
                  <MonacoDiffEditor
                    height="500px"
                    language="json"
                    original={JSON.stringify(originalVariablesRef.current, null, 2)}
                    modified={JSON.stringify(currentApiVariables, null, 2)}
                  />
                </div>
              </TabsContent>
            </Tabs>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCompareVisible(false)}>关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default TemplateEdit
