import { useState, type ReactNode } from 'react'
import { Card, CardContent } from '@/shared/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'

interface WorldRestoreSidebarProps {
  mapInitialized: boolean
  backup: ReactNode
  claims?: ReactNode
  players: ReactNode
}

export function WorldRestoreSidebar({
  mapInitialized,
  backup,
  claims,
  players,
}: WorldRestoreSidebarProps) {
  const [tab, setTab] = useState('backup')
  const activeTab = !mapInitialized || (tab === 'claims' && !claims) ? 'backup' : tab

  return (
    <div className="flex flex-col min-w-0 md:min-h-0 md:overflow-y-auto md:*:shrink-0">
      <Card>
        <CardContent>
          <Tabs
            value={activeTab}
            onValueChange={value => {
              if (value === 'backup' || value === 'claims' || value === 'players') setTab(value)
            }}
            className="gap-4"
          >
            {mapInitialized && (
              <TabsList className={claims ? 'grid w-full grid-cols-3' : 'grid w-full grid-cols-2'}>
                <TabsTrigger value="backup">备份与恢复</TabsTrigger>
                {claims && <TabsTrigger value="claims">领地列表</TabsTrigger>}
                <TabsTrigger value="players">玩家位置</TabsTrigger>
              </TabsList>
            )}
            <TabsContent value="backup" keepMounted>
              {backup}
            </TabsContent>
            <TabsContent value="claims">{mapInitialized && claims}</TabsContent>
            <TabsContent value="players">{mapInitialized && players}</TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}
