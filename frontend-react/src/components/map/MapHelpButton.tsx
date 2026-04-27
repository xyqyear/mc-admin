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
              <div className="mb-1 font-medium">查看地图</div>
              <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                <li>按住鼠标左键/中键拖动：平移视角</li>
                <li>滚轮：缩放</li>
              </ul>
            </section>
            <section>
              <div className="mb-1 font-medium">添加选区</div>
              <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                <li>Ctrl + 鼠标左键单击：添加光标处的区域 / 区块</li>
                <li>Ctrl + 鼠标左键拖拽：框选添加</li>
              </ul>
            </section>
            <section>
              <div className="mb-1 font-medium">取消选区</div>
              <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                <li>鼠标右键单击：移除光标处的区域 / 区块</li>
                <li>鼠标右键拖拽：框选移除</li>
              </ul>
            </section>
            <section>
              <div className="mb-1 font-medium">清空选区</div>
              <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                <li>地图聚焦后按 Esc 键</li>
              </ul>
            </section>
            <section>
              <div className="mb-1 font-medium">移动端</div>
              <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                <li>地图右上工具栏切换 平移 / 添加 / 擦除，再用单指点击或拖动操作</li>
              </ul>
            </section>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default MapHelpButton
