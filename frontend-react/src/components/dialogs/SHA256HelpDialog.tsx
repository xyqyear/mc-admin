import React from 'react'
import { Shield, Info } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'

interface SHA256HelpDialogProps {
  open: boolean
  onCancel: () => void
}

const SHA256HelpDialog: React.FC<SHA256HelpDialogProps> = ({
  open,
  onCancel,
}) => {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-175 max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Windows SHA256 校验指南
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          <Alert>
            <Info className="h-4 w-4" />
            <AlertTitle>为什么要检查SHA256？</AlertTitle>
            <AlertDescription>
              SHA256校验可以确保文件在传输过程中没有损坏或被篡改，保证文件的完整性和安全性。
            </AlertDescription>
          </Alert>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Windows 系统操作步骤</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex gap-3">
                <div className="flex shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground h-6 w-6 text-xs font-medium">1</div>
                <div className="space-y-2">
                  <p className="font-medium">获取文件路径</p>
                  <p className="text-sm text-muted-foreground">
                    在文件管理器中找到下载的压缩包文件，<strong>右键点击文件</strong>
                  </p>
                  <p className="text-sm text-muted-foreground">
                    选择 <code className="bg-muted px-1 py-0.5 rounded text-xs">复制文件地址</code> 或 <code className="bg-muted px-1 py-0.5 rounded text-xs">复制为路径</code>
                  </p>
                  <Alert>
                    <Info className="h-4 w-4" />
                    <AlertTitle>提示</AlertTitle>
                    <AlertDescription>
                      不同版本的Windows可能显示为&ldquo;复制文件地址&rdquo;或&ldquo;复制为路径&rdquo;，选择其中任意一个即可。
                    </AlertDescription>
                  </Alert>
                </div>
              </div>

              <div className="flex gap-3">
                <div className="flex shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground h-6 w-6 text-xs font-medium">2</div>
                <div className="space-y-2">
                  <p className="font-medium">打开命令提示符</p>
                  <p className="text-sm text-muted-foreground">
                    按 <code className="bg-muted px-1 py-0.5 rounded text-xs">Win + R</code> 键，输入 <code className="bg-muted px-1 py-0.5 rounded text-xs">cmd</code> 并按回车
                  </p>
                  <p className="text-sm text-muted-foreground">
                    或者在开始菜单搜索 <code className="bg-muted px-1 py-0.5 rounded text-xs">命令提示符</code> 并打开
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <div className="flex shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground h-6 w-6 text-xs font-medium">3</div>
                <div className="space-y-2">
                  <p className="font-medium">执行SHA256计算命令</p>
                  <p className="text-sm text-muted-foreground">在命令提示符中输入以下命令：</p>
                  <div className="bg-muted p-3 rounded border font-mono text-sm">
                    certutil -hashfile &ldquo;文件路径&rdquo; SHA256
                  </div>
                  <p className="text-sm text-muted-foreground">
                    将 <code className="bg-muted px-1 py-0.5 rounded text-xs">&ldquo;文件路径&rdquo;</code> 替换为第一步复制的文件路径，然后按回车执行
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <div className="flex shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground h-6 w-6 text-xs font-medium">4</div>
                <div className="space-y-2">
                  <p className="font-medium">对比SHA256值</p>
                  <p className="text-sm text-muted-foreground">命令执行后会显示文件的SHA256值</p>
                  <p className="text-sm text-muted-foreground">将显示的SHA256值与本系统中显示的SHA256值进行对比</p>
                  <Alert>
                    <AlertTitle>验证结果</AlertTitle>
                    <AlertDescription>
                      <div><strong className="text-green-600">✓ 如果两个值完全相同</strong>：文件完整，可以安全使用</div>
                      <div><strong className="text-red-600">✗ 如果两个值不同</strong>：文件可能已损坏，请重新下载</div>
                    </AlertDescription>
                  </Alert>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <Info className="h-4 w-4" />
                命令示例
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm">
                <strong>示例文件路径：</strong>{' '}
                <code className="bg-muted px-1 py-0.5 rounded text-xs">C:\Users\用户名\Downloads\server.zip</code>
              </p>
              <p className="text-sm"><strong>完整命令：</strong></p>
              <div className="bg-muted p-3 rounded border font-mono text-sm">
                certutil -hashfile &ldquo;C:\Users\用户名\Downloads\server.zip&rdquo; SHA256
              </div>
              <p className="text-sm"><strong>输出示例：</strong></p>
              <div className="bg-muted p-3 rounded border font-mono text-sm">
                <div>SHA256 哈希(文件 C:\Users\用户名\Downloads\server.zip):</div>
                <div>dc4f775377b597f5cb10d7debd52c028f3219a5da50b23c8055fc33ddcfb68cb</div>
                <div>CertUtil: -hashfile 命令已成功完成。</div>
              </div>
            </CardContent>
          </Card>

          <Alert>
            <Info className="h-4 w-4" />
            <AlertTitle>其他操作系统</AlertTitle>
            <AlertDescription>
              <div><strong>macOS：</strong> 使用终端执行 <code className="bg-muted px-1 py-0.5 rounded text-xs">shasum -a 256 &ldquo;文件路径&rdquo;</code></div>
              <div><strong>Linux：</strong> 使用终端执行 <code className="bg-muted px-1 py-0.5 rounded text-xs">sha256sum &ldquo;文件路径&rdquo;</code></div>
            </AlertDescription>
          </Alert>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default SHA256HelpDialog
