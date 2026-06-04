import React, { useEffect, useState, useRef } from "react"
import { useNavigate } from 'react-router'
import { toast } from "sonner"
import { ArrowLeft, Save, Settings, GitCompare } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"
import { Spinner } from "@/components/ui/spinner"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"

import PageHeader from "@/components/layout/PageHeader"
import LoadingSpinner from "@/components/layout/LoadingSpinner"
import { MonacoDiffEditor } from "@/components/editors"
import {
  VariableDefinitionForm,
  convertToFormData,
  convertToApiFormat,
  type VariableFormData,
} from "@/components/templates"
import { useDefaultVariables } from "@/hooks/queries/base/useTemplateQueries"
import { useTemplateMutations } from "@/hooks/mutations/useTemplateMutations"
import type { VariableDefinition } from "@/hooks/api/templateApi"

const DefaultVariables: React.FC = () => {
  const navigate = useNavigate()

  const { data: defaultVariablesData, isLoading, refetch } = useDefaultVariables()
  const { useUpdateDefaultVariables } = useTemplateMutations()
  const updateMutation = useUpdateDefaultVariables()

  const [variables, setVariables] = useState<VariableFormData[]>([])
  const [isCompareVisible, setIsCompareVisible] = useState(false)
  const originalVariablesRef = useRef<VariableDefinition[]>([])

  useEffect(() => {
    if (defaultVariablesData?.variable_definitions) {
      originalVariablesRef.current = defaultVariablesData.variable_definitions
      setVariables(convertToFormData(defaultVariablesData.variable_definitions))
    }
  }, [defaultVariablesData])

  const duplicateErrors = React.useMemo(() => {
    const varNames = variables.map((v) => v.name).filter(Boolean)
    const duplicates = varNames.filter((n, i) => varNames.indexOf(n) !== i)
    if (duplicates.length > 0) {
      return [`变量名重复: ${[...new Set(duplicates)].join(", ")}`]
    }
    return []
  }, [variables])

  const handleCompare = async () => {
    try {
      const result = await refetch()
      if (result.data?.variable_definitions) {
        originalVariablesRef.current = result.data.variable_definitions
      }
      setIsCompareVisible(true)
    } catch {
      toast.warning("获取最新配置失败，使用当前缓存的配置进行对比")
      setIsCompareVisible(true)
    }
  }

  const handleSave = async () => {
    if (duplicateErrors.length > 0) {
      toast.error("请先修复验证错误")
      return
    }

    const apiVariables = convertToApiFormat(variables)
    await updateMutation.mutateAsync(apiVariables)
  }

  if (isLoading) {
    return <LoadingSpinner />
  }

  const currentApiVariables = convertToApiFormat(variables)

  return (
    <div className="space-y-4">
      <PageHeader title="默认变量配置" icon={<Settings className="h-5 w-5" />} />

      <Card>
        <CardContent className="pt-6">
          <Alert className="mb-4">
            <AlertTitle>默认变量配置</AlertTitle>
            <AlertDescription>
              这些变量将在创建新模板时自动预填充到变量列表中。填充后与普通变量无异，可以自由修改或删除。
            </AlertDescription>
          </Alert>

          <VariableDefinitionForm
            value={variables}
            onChange={setVariables}
            title="默认变量列表"
          />

          {duplicateErrors.length > 0 && (
            <Alert variant="destructive" className="mt-4">
              <AlertTitle>验证错误</AlertTitle>
              <AlertDescription>
                <ul className="list-disc pl-4">
                  {duplicateErrors.map((error, index) => (
                    <li key={index}>{error}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          <div className="flex justify-between mt-4">
            <Button variant="outline" onClick={() => navigate(-1)}>
              <ArrowLeft className="mr-1 h-4 w-4" />
              返回
            </Button>
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={handleCompare}>
                <GitCompare className="mr-1 h-4 w-4" />
                差异对比
              </Button>
              <Button
                onClick={handleSave}
                disabled={updateMutation.isPending || duplicateErrors.length > 0}
              >
                {updateMutation.isPending && <Spinner className="mr-2 size-4" />}
                <Save className="mr-1 h-4 w-4" />
                保存
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Dialog open={isCompareVisible} onOpenChange={(o) => !o && setIsCompareVisible(false)}>
        <DialogContent className="sm:max-w-300">
          <DialogHeader>
            <DialogTitle>配置差异对比</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Alert>
              <AlertTitle>差异对比视图</AlertTitle>
              <AlertDescription>左侧为服务器当前配置，右侧为本地编辑的配置。高亮显示的是差异部分。</AlertDescription>
            </Alert>
            <div className="border rounded-md overflow-hidden h-150">
              <MonacoDiffEditor
                height="600px"
                language="json"
                original={JSON.stringify(originalVariablesRef.current, null, 2)}
                modified={JSON.stringify(currentApiVariables, null, 2)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCompareVisible(false)}>关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default DefaultVariables
