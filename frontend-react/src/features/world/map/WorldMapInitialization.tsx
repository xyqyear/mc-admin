import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { Card, CardContent } from '@/shared/ui/card'
import type { WorldMapController } from '@/features/world/useWorldMapController'

interface WorldMapInitializationProps {
  map: Pick<WorldMapController['map'], 'mapStatusQ' | 'mapInitialized' | 'openInitDialog'>
  showStatusError?: boolean
}

export function WorldMapInitialization({ map, showStatusError = false }: WorldMapInitializationProps) {
  const { mapStatusQ, mapInitialized, openInitDialog } = map
  return (
    <>
      {showStatusError && mapStatusQ.isError && (
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法获取地图初始化状态</AlertDescription>
        </Alert>
      )}
      {!mapStatusQ.isLoading && mapStatusQ.data && !mapInitialized && (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-8">
            <div className="text-center text-muted-foreground">
              {!mapStatusQ.data.client_jar_present
                ? '尚未下载客户端 JAR。'
                : !mapStatusQ.data.palette_present
                  ? '尚未生成调色板。'
                  : '调色板已过期（版本或mods变更）。'}
            </div>
            <Button onClick={() => openInitDialog(false)}>初始化地图</Button>
          </CardContent>
        </Card>
      )}
    </>
  )
}
