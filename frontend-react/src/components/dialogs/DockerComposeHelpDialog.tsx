import React from 'react'
import {
  HelpCircle,
  ExternalLink,
  AlertTriangle,
  Info,
} from 'lucide-react'

import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface DockerComposeHelpDialogProps {
  open: boolean
  onCancel: () => void
  page?: string
}

const DockerComposeHelpDialog: React.FC<DockerComposeHelpDialogProps> = ({
  open,
  onCancel,
  page,
}) => {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-225">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <HelpCircle className="h-5 w-5" />
            Docker Compose 配置指南
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-6 max-h-[70vh] overflow-y-auto">

          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>重要提醒</AlertTitle>
            <AlertDescription>
              请仔细阅读以下配置指南，确保服务器配置正确。错误的配置可能导致服务器无法启动或端口冲突。
            </AlertDescription>
          </Alert>

          {page === 'ServerCompose' && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>配置更新警告</AlertTitle>
              <AlertDescription>
                如果您在设置界面，请注意需要点击【提交并重建】按钮才能应用配置更改。提交并重建会重启服务器，会中断当前游戏。
              </AlertDescription>
            </Alert>
          )}

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Info className="h-4 w-4" /> Docker 镜像与 Java 版本
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <span className="font-semibold">格式：</span> <code className="text-xs bg-muted px-1 py-0.5 rounded">itzg/minecraft-server:[java版本标签]</code>
              </p>
              <p className="font-semibold">常用版本：</p>
              <div className="ml-4 space-y-1">
                <div><Badge variant="outline" className="text-blue-600 border-blue-300">java8</Badge> - Java 8 (适用于较老版本)</div>
                <div><Badge variant="outline" className="text-green-600 border-green-300">java11</Badge> - Java 11 (推荐用于 1.17-1.20)</div>
                <div><Badge variant="outline" className="text-orange-600 border-orange-300">java17</Badge> - Java 17 (推荐用于 1.18+)</div>
                <div><Badge variant="outline" className="text-red-600 border-red-300">java21</Badge> - Java 21 (推荐)</div>
                <div><Badge variant="outline" className="text-red-600 border-red-300">java25</Badge> - Java 25 (推荐用于1.21.10+)</div>
              </div>
              <p>
                <ExternalLink className="inline h-3.5 w-3.5 mr-1" />
                <span className="font-semibold">详细版本参考：</span>{' '}
                <a href="https://docker-minecraft-server.readthedocs.io/en/latest/versions/java/" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                  Java 版本文档
                </a>
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Info className="h-4 w-4" /> 容器名称 (container_name)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Alert>
                <AlertTitle>必须格式</AlertTitle>
                <AlertDescription><code className="text-xs bg-muted px-1 py-0.5 rounded">mc-{'{服务器名称}'}</code></AlertDescription>
              </Alert>
              <p className="font-semibold">示例：</p>
              <div className="ml-4 space-y-1">
                <div>服务器名：<code className="text-xs bg-muted px-1 py-0.5 rounded">vanilla</code> → 容器名：<code className="text-xs bg-muted px-1 py-0.5 rounded">mc-vanilla</code></div>
                <div>服务器名：<code className="text-xs bg-muted px-1 py-0.5 rounded">fabric-server</code> → 容器名：<code className="text-xs bg-muted px-1 py-0.5 rounded">mc-fabric-server</code></div>
                <div>服务器名：<code className="text-xs bg-muted px-1 py-0.5 rounded">paper-1-20</code> → 容器名：<code className="text-xs bg-muted px-1 py-0.5 rounded">mc-paper-1-20</code></div>
              </div>
            </CardContent>
          </Card>

          <Separator />

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Info className="h-4 w-4" /> 环境变量 (environment)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div>
                <h5 className="font-semibold mb-2">基础配置</h5>
                <div className="space-y-2 ml-4">
                  <div><span className="font-semibold">VERSION:</span> 游戏版本 (如: <code className="text-xs bg-muted px-1 py-0.5 rounded">1.20.1</code>, <code className="text-xs bg-muted px-1 py-0.5 rounded">1.19.4</code>, <code className="text-xs bg-muted px-1 py-0.5 rounded">LATEST</code>)</div>
                  <div><span className="font-semibold">INIT_MEMORY:</span> 初始内存 (推荐: <code className="text-xs bg-muted px-1 py-0.5 rounded">2G</code> 或 <code className="text-xs bg-muted px-1 py-0.5 rounded">0G</code>)</div>
                  <div>
                    <span className="font-semibold">MAX_MEMORY:</span> 最大堆内存 (如: <code className="text-xs bg-muted px-1 py-0.5 rounded">4G</code>, <code className="text-xs bg-muted px-1 py-0.5 rounded">8G</code>)
                    <Alert variant="destructive" className="mt-2">
                      <AlertTriangle className="h-4 w-4" />
                      <AlertTitle>内存警告</AlertTitle>
                      <AlertDescription>请在总览页面检查系统内存是否充足再启动服务器</AlertDescription>
                    </Alert>
                  </div>
                </div>
              </div>

              <div>
                <h5 className="font-semibold mb-2">服务器类型</h5>
                <p><span className="font-semibold">TYPE:</span> 服务器类型，决定使用的服务端</p>
                <div className="ml-4 space-y-1 mt-1">
                  <div><Badge variant="outline">VANILLA</Badge> - 原版服务器</div>
                  <div><Badge variant="outline" className="text-blue-600 border-blue-300">PAPER</Badge> - Paper 服务器 (性能优化)</div>
                  <div><Badge variant="outline" className="text-green-600 border-green-300">FABRIC</Badge> - Fabric 模组服务器</div>
                  <div><Badge variant="outline" className="text-orange-600 border-orange-300">FORGE</Badge> - Forge 模组服务器</div>
                  <div><Badge variant="outline" className="text-red-600 border-red-300">NEOFORGE</Badge> - NeoForge 模组服务器</div>
                </div>
              </div>

              <div>
                <h5 className="font-semibold mb-2">模组加载器版本设置</h5>
                <div className="space-y-2 ml-4">
                  <div>
                    <span className="font-semibold">Fabric 服务器：</span>
                    <div className="ml-4">
                      <div><code className="text-xs bg-muted px-1 py-0.5 rounded">FABRIC_LAUNCHER_VERSION:</code> Fabric 启动器版本</div>
                      <div><code className="text-xs bg-muted px-1 py-0.5 rounded">FABRIC_LOADER_VERSION:</code> Fabric 加载器版本</div>
                    </div>
                  </div>
                  <div>
                    <span className="font-semibold">Forge 服务器：</span>
                    <div className="ml-4">
                      <div><code className="text-xs bg-muted px-1 py-0.5 rounded">FORGE_VERSION:</code> Forge 版本</div>
                    </div>
                  </div>
                  <div>
                    <span className="font-semibold">NeoForge 服务器：</span>
                    <div className="ml-4">
                      <div><code className="text-xs bg-muted px-1 py-0.5 rounded">NEOFORGE_VERSION:</code> NeoForge 版本</div>
                    </div>
                  </div>
                </div>
              </div>

              <p>
                <ExternalLink className="inline h-3.5 w-3.5 mr-1" />
                <span className="font-semibold">详细配置参考：</span>{' '}
                <a href="https://docker-minecraft-server.readthedocs.io/en/latest/types-and-platforms/" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                  服务器类型文档
                </a>
                （在左侧菜单选择对应的模组加载器）
              </p>
            </CardContent>
          </Card>

          <Separator />

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Info className="h-4 w-4" /> 端口配置 (ports)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <span className="font-semibold">格式：</span> <code className="text-xs bg-muted px-1 py-0.5 rounded">[外部端口]:[容器内部端口]</code> 注意请不要修改容器内部端口
              </p>
              <div className="space-y-2 ml-4">
                <div>
                  <span className="font-semibold">游戏端口：</span> <code className="text-xs bg-muted px-1 py-0.5 rounded">25565:25565</code>
                  <br />
                  <span className="text-muted-foreground">修改左侧端口避免与现有服务器冲突（如: 25566, 25567）</span>
                </div>
                <div>
                  <span className="font-semibold">RCON端口：</span> <code className="text-xs bg-muted px-1 py-0.5 rounded">25575:25575</code>
                  <br />
                  <span className="text-muted-foreground">用于远程管理，同样需要避免端口冲突</span>
                </div>
              </div>
              <Alert className="mt-2">
                <Info className="h-4 w-4" />
                <AlertTitle>端口冲突检查</AlertTitle>
                <AlertDescription>请确保选择的外部端口不与系统中其他服务器或服务冲突</AlertDescription>
              </Alert>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Info className="h-4 w-4" /> 其他重要配置
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>卷挂载 (volumes)</AlertTitle>
                <AlertDescription>必须保持为 <code className="text-xs bg-muted px-1 py-0.5 rounded">./data:/data</code>，请不要修改此配置</AlertDescription>
              </Alert>
              <Alert>
                <Info className="h-4 w-4" />
                <AlertTitle>容器选项</AlertTitle>
                <AlertDescription>以下选项请保持不变：<code className="text-xs bg-muted px-1 py-0.5 rounded">stdin_open: true</code>、<code className="text-xs bg-muted px-1 py-0.5 rounded">tty: true</code>、<code className="text-xs bg-muted px-1 py-0.5 rounded">restart: unless-stopped</code></AlertDescription>
              </Alert>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Info className="h-4 w-4" /> 配置示例
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm">
              <h5 className="font-semibold mb-2">Forge 1.20.1 服务器示例</h5>
              <pre className="bg-muted p-4 rounded text-xs overflow-x-auto">
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
            </CardContent>
          </Card>

        </div>
      </DialogContent>
    </Dialog>
  )
}

export default DockerComposeHelpDialog
