import React, { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Card,
  Button,
  Alert,
  Modal,
  Select,
  Typography,
  Divider,
  Spin,
  App
} from 'antd'
import {
  SettingOutlined,
  ReloadOutlined,
  DiffOutlined,
  SaveOutlined,
  UndoOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons'
import Form from '@/components/forms/rjsfTheme'
import validator from '@rjsf/validator-ajv8'
import { MonacoDiffEditor } from '@/components/editors'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import PageHeader from '@/components/layout/PageHeader'
import { useConfigModules, useModuleConfig, useModuleSchema } from '@/hooks/queries/base/useConfigQueries'
import { useUpdateModuleConfig, useResetModuleConfig } from '@/hooks/mutations/useConfigMutations'
import { RJSFSchema } from '@rjsf/utils'

const { Title, Text } = Typography

const DynamicConfig: React.FC = () => {
  const { message, modal } = App.useApp()
  const [searchParams, setSearchParams] = useSearchParams()
  const [selectedModule, setSelectedModule] = useState<string | null>(null)
  const [formData, setFormData] = useState<any>({})
  const [isCompareVisible, setIsCompareVisible] = useState(false)

  // API hooks
  const { data: modules, isLoading: modulesLoading, error: modulesError } = useConfigModules()
  const {
    data: moduleConfig,
    isLoading: configLoading,
    error: configError,
    refetch: refetchConfig
  } = useModuleConfig(selectedModule)
  const {
    data: moduleSchema,
    isLoading: schemaLoading,
    error: schemaError
  } = useModuleSchema(selectedModule)

  const updateConfigMutation = useUpdateModuleConfig()
  const resetConfigMutation = useResetModuleConfig()

  // Initialize selected module from URL params
  useEffect(() => {
    const moduleParam = searchParams.get('module')
    if (moduleParam && moduleParam !== selectedModule) {
      setSelectedModule(moduleParam)
    }
  }, [searchParams, selectedModule])

  // Update form data when config loads
  useEffect(() => {
    if (moduleConfig?.config_data) {
      setFormData(moduleConfig.config_data)
    }
  }, [moduleConfig])

  // Handle module selection
  const handleModuleChange = (moduleName: string) => {
    setSelectedModule(moduleName)
    setFormData({})

    // Update URL params to reflect module selection
    const newParams = new URLSearchParams(searchParams)
    if (moduleName) {
      newParams.set('module', moduleName)
    } else {
      newParams.delete('module')
    }
    setSearchParams(newParams)
  }

  // Handle form data change
  const handleFormChange = ({ formData: newFormData }: any) => {
    setFormData(newFormData)
  }

  // Handle reload configuration
  const handleReloadConfig = async () => {
    modal.confirm({
      title: '重新载入配置',
      content: '确定要重新载入配置吗？这将丢失当前表单中的更改，恢复到服务器的配置。',
      okText: '确认',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        try {
          const refreshedConfig = await refetchConfig()
          if (refreshedConfig.data?.config_data) {
            setFormData(refreshedConfig.data.config_data)
          }
          message.info('配置已重新载入')
        } catch (error: any) {
          message.error(`重新载入失败: ${error.message}`)
        }
      }
    })
  }

  // Handle reset to defaults
  const handleResetToDefaults = () => {
    if (!selectedModule) return

    modal.confirm({
      title: '重置为默认配置',
      content: '确定要将配置重置为默认值吗？这将覆盖所有当前设置。',
      okText: '确认重置',
      okType: 'danger',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        try {
          const result = await resetConfigMutation.mutateAsync(selectedModule)
          if (result.updated_config) {
            setFormData(result.updated_config)
          }
        } catch (error: any) {
          // Error handling is already done in the mutation
          console.error('Reset config failed:', error)
        }
      }
    })
  }

  // Handle submit configuration
  const handleSubmitConfig = async () => {
    if (!selectedModule || !moduleConfig) return

    // Show loading message and refresh config first
    const hideLoading = message.loading('正在获取最新配置...', 0)
    let latestConfig = moduleConfig

    try {
      const refreshedConfig = await refetchConfig()
      if (refreshedConfig.data) {
        latestConfig = refreshedConfig.data
      }
    } catch {
      message.warning('获取最新配置失败，将使用当前缓存的配置进行对比')
    } finally {
      hideLoading()
    }

    // Check for changes using the latest config
    const hasChanges = JSON.stringify(formData) !== JSON.stringify(latestConfig.config_data)

    modal.confirm({
      title: '提交配置更改',
      content: (
        <div className="space-y-4">
          <p>确定要提交配置更改吗？</p>
          {hasChanges && (
            <div>
              <div className="mb-2">
                <strong>配置差异预览：</strong>
              </div>
              <div style={{
                border: '1px solid #d9d9d9',
                borderRadius: '6px',
                overflow: 'hidden',
                height: '400px',
                backgroundColor: '#fafafa'
              }}>
                <MonacoDiffEditor
                  height="400px"
                  language="json"
                  original={JSON.stringify(latestConfig.config_data, null, 2)}
                  modified={JSON.stringify(formData, null, 2)}
                  theme="vs-light"
                  options={{
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    fontSize: 12,
                    lineNumbers: 'off',
                    folding: false,
                    wordWrap: 'on',
                    scrollbar: {
                      vertical: 'visible',
                      horizontal: 'visible'
                    }
                  }}
                />
              </div>
            </div>
          )}
          {!hasChanges && (
            <Alert
              title="没有检测到配置更改"
              description="当前表单配置与服务器配置相同，提交后不会有任何变化。"
              type="info"
              showIcon
              className="mt-2"
            />
          )}
        </div>
      ),
      width: 800,
      okText: '确认提交',
      okType: hasChanges ? 'primary' : 'default',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        await updateConfigMutation.mutateAsync({
          moduleName: selectedModule,
          configData: formData
        })
      }
    })
  }

  // Handle compare configuration
  const handleCompareConfig = async () => {
    const hideLoading = message.loading('正在获取最新配置...', 0)

    try {
      await refetchConfig()
      setIsCompareVisible(true)
    } catch {
      message.warning('获取最新配置失败，使用当前缓存的配置进行对比')
      setIsCompareVisible(true)
    } finally {
      hideLoading()
    }
  }

  // Loading state
  if (modulesLoading) {
    return <LoadingSpinner height="16rem" tip="加载配置模块中..." />
  }

  // Error state
  if (modulesError) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert
          title="加载失败"
          description="无法加载动态配置模块"
          type="error"
          showIcon
        />
      </div>
    )
  }

  const moduleOptions = Object.entries(modules?.modules || {}).map(([key, module]) => ({
    label: `${module.module_name} (${module.schema_class})`,
    value: key
  }))

  const isConfigLoaded = moduleConfig && moduleSchema && !configLoading && !schemaLoading

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader
        title="动态配置管理"
        icon={<SettingOutlined />}
        actions={
          selectedModule && isConfigLoaded ? (
            <>
              <Button
                icon={<DiffOutlined />}
                onClick={handleCompareConfig}
              >
                差异对比
              </Button>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleReloadConfig}
              >
                重新载入
              </Button>
              <Button
                danger
                icon={<UndoOutlined />}
                onClick={handleResetToDefaults}
                loading={resetConfigMutation.isPending}
              >
                重置默认
              </Button>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSubmitConfig}
                loading={updateConfigMutation.isPending}
              >
                提交更改
              </Button>
            </>
          ) : null
        }
      />

      <div style={{ height: '1rem' }} />

      <Card
        title="选择配置模块"
        style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
        styles={{ body: { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' } }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <Select
            placeholder="请选择一个配置模块"
            style={{ width: '100%', marginBottom: 16 }}
            options={moduleOptions}
            value={selectedModule}
            onChange={handleModuleChange}
            loading={modulesLoading}
          />

          {selectedModule && (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
              <Divider style={{ margin: '16px 0' }} />

              {/* Loading state for config/schema */}
              {(configLoading || schemaLoading) && (
                <div className="flex justify-center">
                  <Spin>
                    <div className="p-8 text-center text-gray-500">
                      加载配置中...
                    </div>
                  </Spin>
                </div>
              )}

              {/* Error states */}
              {configError && (
                <Alert
                  title="配置加载失败"
                  description="无法加载选定模块的配置数据"
                  type="error"
                  showIcon
                  style={{ marginBottom: 16 }}
                />
              )}

              {schemaError && (
                <Alert
                  title="模式加载失败"
                  description="无法加载选定模块的配置模式"
                  type="error"
                  showIcon
                  style={{ marginBottom: 16 }}
                />
              )}

              {/* Configuration form */}
              {isConfigLoaded && (
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                  <div style={{ marginBottom: 16 }}>
                    <Title level={4} style={{ margin: 0 }}>配置表单</Title>
                    <Text type="secondary">
                      模块: {moduleSchema.module_name} |
                      版本: {moduleSchema.version} |
                      类型: {moduleSchema.schema_class}
                    </Text>
                  </div>

                  <Card
                    style={{ flex: 1, minHeight: 0 }}
                    styles={{ body: { height: '100%', overflow: 'auto' } }}
                  >
                    <Form
                      schema={moduleSchema.json_schema as RJSFSchema}
                      formData={formData}
                      validator={validator}
                      onChange={handleFormChange}
                      onSubmit={handleSubmitConfig}
                      onError={(errors) => console.log('Form validation errors:', errors)}
                      liveValidate="onChange"
                    >
                      <div />
                    </Form>
                  </Card>
                </div>
              )}
            </div>
          )}
        </div>
      </Card>

      {/* Compare modal */}
      <Modal
        title="配置差异对比"
        open={isCompareVisible}
        onCancel={() => setIsCompareVisible(false)}
        width={1400}
        footer={[
          <Button key="close" onClick={() => setIsCompareVisible(false)}>
            关闭
          </Button>
        ]}
      >
        <div className="space-y-4">
          <Alert
            title="差异对比视图"
            description="左侧为服务器当前配置，右侧为表单编辑的配置。高亮显示的是差异部分。"
            type="info"
            showIcon
          />
          <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden', height: '600px' }}>
            <MonacoDiffEditor
              height="600px"
              language="json"
              original={JSON.stringify(moduleConfig?.config_data || {}, null, 2)}
              modified={JSON.stringify(formData, null, 2)}
              originalTitle="服务器当前配置"
              modifiedTitle="表单编辑配置"
              theme="vs-light"
            />
          </div>
        </div>
      </Modal>

    </div>
  )
}

export default DynamicConfig