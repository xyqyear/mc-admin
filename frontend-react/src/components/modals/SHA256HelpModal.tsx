import React from 'react'
import {
  Modal,
  Alert,
  Typography,
  Card,
  Steps,
} from 'antd'
import {
  InfoCircleOutlined,
  WindowsOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'

const { Text, Paragraph } = Typography

interface SHA256HelpModalProps {
  open: boolean
  onCancel: () => void
}

const SHA256HelpModal: React.FC<SHA256HelpModalProps> = ({
  open,
  onCancel,
}) => {
  return (
    <Modal
      title={
        <div className="flex items-center space-x-2">
          <SafetyCertificateOutlined />
          <span>Windows SHA256 校验指南</span>
        </div>
      }
      open={open}
      onCancel={onCancel}
      width={700}
      footer={null}
      style={{ top: 20 }}
    >
      <div className="space-y-6 max-h-[70vh] overflow-y-auto">

        {/* 重要提醒 */}
        <Alert
          message="为什么要检查SHA256？"
          description="SHA256校验可以确保文件在传输过程中没有损坏或被篡改，保证文件的完整性和安全性。"
          type="info"
          showIcon
          icon={<InfoCircleOutlined />}
        />

        {/* Windows 操作步骤 */}
        <Card size="small" title={<Text strong><WindowsOutlined /> Windows 系统操作步骤</Text>}>
          <Steps
            direction="vertical"
            size="small"
            items={[
              {
                title: '获取文件路径',
                description: (
                  <div className="space-y-2">
                    <Paragraph>
                      在文件管理器中找到下载的压缩包文件，<Text strong>右键点击文件</Text>
                    </Paragraph>
                    <Paragraph>
                      选择 <Text code>复制文件地址</Text> 或 <Text code>复制为路径</Text>
                    </Paragraph>
                    <Alert
                      message="提示"
                      description="不同版本的Windows可能显示为&quot;复制文件地址&quot;或&quot;复制为路径&quot;，选择其中任意一个即可。"
                      type="info"
                      showIcon
                    />
                  </div>
                ),
                icon: <FileTextOutlined />,
              },
              {
                title: '打开命令提示符',
                description: (
                  <div className="space-y-2">
                    <Paragraph>
                      按 <Text code>Win + R</Text> 键，输入 <Text code>cmd</Text> 并按回车
                    </Paragraph>
                    <Paragraph>
                      或者在开始菜单搜索 <Text code>命令提示符</Text> 并打开
                    </Paragraph>
                  </div>
                ),
                icon: <WindowsOutlined />,
              },
              {
                title: '执行SHA256计算命令',
                description: (
                  <div className="space-y-2">
                    <Paragraph>
                      在命令提示符中输入以下命令：
                    </Paragraph>
                    <div className="bg-gray-50 p-3 rounded border font-mono text-sm">
                      <Text code>certutil -hashfile &quot;文件路径&quot; SHA256</Text>
                    </div>
                    <Paragraph>
                      将 <Text code>&quot;文件路径&quot;</Text> 替换为第一步复制的文件路径，然后按回车执行
                    </Paragraph>
                  </div>
                ),
                icon: <SafetyCertificateOutlined />,
              },
              {
                title: '对比SHA256值',
                description: (
                  <div className="space-y-2">
                    <Paragraph>
                      命令执行后会显示文件的SHA256值
                    </Paragraph>
                    <Paragraph>
                      将显示的SHA256值与本系统中显示的SHA256值进行对比
                    </Paragraph>
                    <Alert
                      message="验证结果"
                      description={
                        <div>
                          <div><Text strong className="text-green-600">✓ 如果两个值完全相同</Text>：文件完整，可以安全使用</div>
                          <div><Text strong className="text-red-600">✗ 如果两个值不同</Text>：文件可能已损坏，请重新下载</div>
                        </div>
                      }
                      type="warning"
                      showIcon
                      style={{ marginTop: 8 }}
                    />
                  </div>
                ),
                icon: <InfoCircleOutlined />,
              },
            ]}
          />
        </Card>

        {/* 命令示例 */}
        <Card size="small" title={<Text strong><InfoCircleOutlined /> 命令示例</Text>}>
          <Paragraph>
            <Text strong>示例文件路径：</Text> <Text code>C:\Users\用户名\Downloads\server.zip</Text>
          </Paragraph>
          <Paragraph>
            <Text strong>完整命令：</Text>
          </Paragraph>
          <div className="bg-gray-50 p-3 rounded border font-mono text-sm">
            <Text code>certutil -hashfile &quot;C:\Users\用户名\Downloads\server.zip&quot; SHA256</Text>
          </div>
          <Paragraph style={{ marginTop: 12 }}>
            <Text strong>输出示例：</Text>
          </Paragraph>
          <div className="bg-gray-50 p-3 rounded border font-mono text-sm">
            <div>SHA256 哈希(文件 C:\Users\用户名\Downloads\server.zip):</div>
            <div>dc4f775377b597f5cb10d7debd52c028f3219a5da50b23c8055fc33ddcfb68cb</div>
            <div>CertUtil: -hashfile 命令已成功完成。</div>
          </div>
        </Card>

        {/* 其他操作系统提示 */}
        <Alert
          message="其他操作系统"
          description={
            <div>
              <div><Text strong>macOS：</Text> 使用终端执行 <Text code>shasum -a 256 &quot;文件路径&quot;</Text></div>
              <div><Text strong>Linux：</Text> 使用终端执行 <Text code>sha256sum &quot;文件路径&quot;</Text></div>
            </div>
          }
          type="info"
          showIcon
        />

      </div>
    </Modal>
  )
}

export default SHA256HelpModal