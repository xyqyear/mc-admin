import React, { useState } from 'react'
import { CircleHelp } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

export const MapHelpButton: React.FC = () => {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button
        variant="outline"
        size="icon"
        className="rounded-full"
        aria-label="操作说明"
        onClick={() => setOpen(true)}
      >
        <CircleHelp className="h-4 w-4" />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>地图操作说明</DialogTitle>
            <DialogDescription>
              使用下列手势查看地图并管理选区。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <section>
              <div className="mb-1 font-medium">地图右上工具栏</div>
              <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                <li>平移：拖动地图，缩放手势照常生效</li>
                <li>添加：单击 / 拖动以添加区域或区块到选区</li>
                <li>擦除：单击 / 拖动以从选区中移除</li>
                <li>垃圾桶：清空当前选区</li>
              </ul>
            </section>
            <section>
              <div className="mb-1 font-medium">查看地图</div>
              <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                <li>桌面：左键拖动平移、滚轮缩放</li>
                <li>触摸：单指拖动平移、双指捏合缩放</li>
              </ul>
            </section>
            <section>
              <div className="mb-1 font-medium">桌面快捷方式</div>
              <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                <li>Ctrl + 左键单击 / 拖拽：添加（不受工具影响）</li>
                <li>右键单击 / 拖拽：移除（不受工具影响）</li>
                <li>地图聚焦后按 Esc：清空选区</li>
              </ul>
            </section>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default MapHelpButton
