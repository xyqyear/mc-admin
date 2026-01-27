import React from 'react'
import {
  Modal,
  Alert,
  Typography,
  Divider,
  Tag,
  Card,
} from 'antd'
import {
  QuestionCircleOutlined,
  LinkOutlined,
  WarningOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface DockerComposeHelpModalProps {
  open: boolean
  onCancel: () => void
  page?: string
}

const DockerComposeHelpModal: React.FC<DockerComposeHelpModalProps> = ({
  open,
  onCancel,
  page,
}) => {
  return (
    <Modal
      title={
        <div className="flex items-center space-x-2">
          <QuestionCircleOutlined />
          <span>Docker Compose 配置指南</span>
        </div>
      }
      open={open}
      onCancel={onCancel}
      width={900}
      footer={null}
      style={{ top: 20 }}
    >
      <div className="space-y-6 max-h-[70vh] overflow-y-auto">

        {/* 重要提醒 */}
        <Alert
          title="重要提醒"
          description="请仔细阅读以下配置指南，确保服务器配置正确。错误的配置可能导致服务器无法启动或端口冲突。"
          type="warning"
          showIcon
          icon={<WarningOutlined />}
        />

        {/* ServerCompose 页面特有警示 */}
        {page === 'ServerCompose' && (
          <Alert
            title="配置更新警告"
            description="如果您在设置界面，请注意需要点击【提交并重建】按钮才能应用配置更改。提交并重建会重启服务器，会中断当前游戏。"
            type="error"
            showIcon
            icon={<WarningOutlined />}
          />
        )}

        {/* Docker 镜像版本 */}
        <Card size="small" title={<Text strong><InfoCircleOutlined /> Docker 镜像与 Java 版本</Text>}>
          <Paragraph>
            <Text strong>格式：</Text> <Text code>itzg/minecraft-server:[java版本标签]</Text>
          </Paragraph>
          <Paragraph>
            <Text strong>常用版本：</Text>
          </Paragraph>
          <div className="ml-4 space-y-1">
            <div><Tag color="blue">java8</Tag> - Java 8 (适用于较老版本)</div>
            <div><Tag color="green">java11</Tag> - Java 11 (推荐用于 1.17-1.20)</div>
            <div><Tag color="orange">java17</Tag> - Java 17 (推荐用于 1.18+)</div>
            <div><Tag color="red">java21</Tag> - Java 21 (推荐)</div>
            <div><Tag color="red">java25</Tag> - Java 25 (推荐用于1.21.10+)</div>
          </div>
          <Paragraph>
            <LinkOutlined /> <Text strong>详细版本参考：</Text>{' '}
            <a href="https://docker-minecraft-server.readthedocs.io/en/latest/versions/java/" target="_blank" rel="noopener noreferrer">
              Java 版本文档
            </a>
          </Paragraph>
        </Card>

        {/* 容器名称 */}
        <Card size="small" title={<Text strong><InfoCircleOutlined /> 容器名称 (container_name)</Text>}>
          <Alert
            title="必须格式"
            description={<Text><Text code>mc-{'{服务器名称}'}</Text></Text>}
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
          />
          <Paragraph>
            <Text strong>示例：</Text>
          </Paragraph>
          <div className="ml-4 space-y-1">
            <div>服务器名：<Text code>vanilla</Text> → 容器名：<Text code>mc-vanilla</Text></div>
            <div>服务器名：<Text code>fabric-server</Text> → 容器名：<Text code>mc-fabric-server</Text></div>
            <div>服务器名：<Text code>paper-1-20</Text> → 容器名：<Text code>mc-paper-1-20</Text></div>
          </div>
        </Card>

        <Divider />

        {/* 环境变量 */}
        <Card size="small" title={<Text strong><InfoCircleOutlined /> 环境变量 (environment)</Text>}>

          {/* 基础配置 */}
          <Title level={5}>基础配置</Title>
          <div className="space-y-3 ml-4">
            <div>
              <Text strong>VERSION:</Text> 游戏版本 (如: <Text code>1.20.1</Text>, <Text code>1.19.4</Text>, <Text code>LATEST</Text>)
            </div>
            <div>
              <Text strong>INIT_MEMORY:</Text> 初始内存 (推荐: <Text code>2G</Text> 或 <Text code>0G</Text>)
            </div>
            <div>
              <Text strong>MAX_MEMORY:</Text> 最大堆内存 (如: <Text code>4G</Text>, <Text code>8G</Text>)
              <br />
              <Alert
                title="内存警告"
                description="请在总览页面检查系统内存是否充足再启动服务器"
                type="warning"
                showIcon
                style={{ marginTop: 8, marginLeft: 0 }}
              />
            </div>
          </div>

          {/* 服务器类型 */}
          <Title level={5} style={{ marginTop: 16 }}>服务器类型</Title>
          <Paragraph>
            <Text strong>TYPE:</Text> 服务器类型，决定使用的服务端
          </Paragraph>
          <div className="ml-4 space-y-2">
            <div><Tag color="default">VANILLA</Tag> - 原版服务器</div>
            <div><Tag color="blue">PAPER</Tag> - Paper 服务器 (性能优化)</div>
            <div><Tag color="green">FABRIC</Tag> - Fabric 模组服务器</div>
            <div><Tag color="orange">FORGE</Tag> - Forge 模组服务器</div>
            <div><Tag color="red">NEOFORGE</Tag> - NeoForge 模组服务器</div>
          </div>

          {/* 模组加载器版本 */}
          <Title level={5} style={{ marginTop: 16 }}>模组加载器版本设置</Title>
          <div className="space-y-3 ml-4">
            <div>
              <Text strong>Fabric 服务器：</Text>
              <div className="ml-4">
                <div><Text code>FABRIC_LAUNCHER_VERSION:</Text> Fabric 启动器版本</div>
                <div><Text code>FABRIC_LOADER_VERSION:</Text> Fabric 加载器版本</div>
              </div>
            </div>
            <div>
              <Text strong>Forge 服务器：</Text>
              <div className="ml-4">
                <div><Text code>FORGE_VERSION:</Text> Forge 版本</div>
              </div>
            </div>
            <div>
              <Text strong>NeoForge 服务器：</Text>
              <div className="ml-4">
                <div><Text code>NEOFORGE_VERSION:</Text> NeoForge 版本</div>
              </div>
            </div>
          </div>

          <Paragraph style={{ marginTop: 12 }}>
            <LinkOutlined /> <Text strong>详细配置参考：</Text>{' '}
            <a href="https://docker-minecraft-server.readthedocs.io/en/latest/types-and-platforms/" target="_blank" rel="noopener noreferrer">
              服务器类型文档
            </a>
            （在左侧菜单选择对应的模组加载器）
          </Paragraph>
        </Card>

        <Divider />

        {/* 端口配置 */}
        <Card size="small" title={<Text strong><InfoCircleOutlined /> 端口配置 (ports)</Text>}>
          <Paragraph>
            <Text strong>格式：</Text> <Text code>[外部端口]:[容器内部端口]</Text> 注意请不要修改容器内部端口
          </Paragraph>
          <div className="space-y-2 ml-4">
            <div>
              <Text strong>游戏端口：</Text> <Text code>25565:25565</Text>
              <br />
              <Text type="secondary">修改左侧端口避免与现有服务器冲突（如: 25566, 25567）</Text>
            </div>
            <div>
              <Text strong>RCON端口：</Text> <Text code>25575:25575</Text>
              <br />
              <Text type="secondary">用于远程管理，同样需要避免端口冲突</Text>
            </div>
          </div>
          <Alert
            title="端口冲突检查"
            description="请确保选择的外部端口不与系统中其他服务器或服务冲突"
            type="info"
            showIcon
            style={{ marginTop: 12 }}
          />
        </Card>

        {/* 其他重要配置 */}
        <Card size="small" title={<Text strong><InfoCircleOutlined /> 其他重要配置</Text>}>
          <div className="space-y-3">
            <Alert
              title="卷挂载 (volumes)"
              description={<Text>必须保持为 <Text code>./data:/data</Text>，请不要修改此配置</Text>}
              type="error"
              showIcon
            />
            <Alert
              title="容器选项"
              description={<Text>以下选项请保持不变：<Text code>stdin_open: true</Text>、<Text code>tty: true</Text>、<Text code>restart: unless-stopped</Text></Text>}
              type="info"
              showIcon
            />
          </div>
        </Card>

        {/* 配置示例 */}
        <Card size="small" title={<Text strong><InfoCircleOutlined /> 配置示例</Text>}>
          <Title level={5}>Forge 1.20.1 服务器示例</Title>
          <pre className="bg-gray-50 p-4 rounded text-sm overflow-x-auto">
            {`services:
  mc:
    image: itzg/minecraft-server:java21
    container_name: mc-server1
    environment:
      EULA: true
      TZ: Asia/Shanghai
      VERSION: 1.20.1
      INIT_MEMORY: 0G
      MAX_MEMORY: 4G
      ONLINE_MODE: true
      TYPE: FORGE
      FORGE_VERSION: 47.4.4
      SPAWN_PROTECTION: 0
      ENABLE_RCON: true
      RCON_PASSWORD: password
      MODE: survival
      VIEW_DISTANCE: 8
      DIFFICULTY: hard
      USE_AIKAR_FLAGS: true
      ENABLE_COMMAND_BLOCK: true
      PREVENT_PROXY_CONNECTIONS: false
      ALLOW_FLIGHT: false
      ENABLE_QUERY: true
    ports:
      - 25517:25565
      - 25617:25575
    volumes:
      - ./data:/data
    stdin_open: true
    tty: true
    restart: unless-stopped`}
          </pre>
        </Card>

      </div>
    </Modal>
  )
}

export default DockerComposeHelpModal