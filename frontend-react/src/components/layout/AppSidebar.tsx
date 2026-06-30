import React, { useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import {
  ShieldCheck,
  LayoutDashboard,
  Database,
  Plus,
  Settings,
  Folder,
  LogOut,
  Code,
  Map as MapIcon,
  Crown,
  UserCog,
  History,
  FileArchive,
  Calendar,
  Globe,
  Users,
  FileText,
  ChevronRight,
  PanelLeftIcon,
  Sun,
  Moon,
  Eraser,
} from 'lucide-react'

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
  useSidebar,
} from '@/components/ui/sidebar'
import {
  Collapsible,
  CollapsibleContent,
} from '@/components/ui/collapsible'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useTheme } from '@/components/theme-provider'
import { cn } from '@/lib/utils'
import { useSidebarStore } from '@/stores/useSidebarStore'
import { useServerQueries } from '@/hooks/queries/base/useServerQueries'
import { useCurrentUser } from '@/hooks/queries/base/useUserQueries'
import { useSelfCheckHealth } from '@/hooks/useSelfCheckHealth'
import { authApi } from '@/hooks/api/authApi'
import { UserRole } from '@/types/User'
import ServerMenuIcon from '@/components/layout/ServerMenuIcon'
import DebugTool from '@/components/debug/DebugTool'

const SERVER_GROUP_KEY = '服务器管理'
const ADMIN_GROUP_KEY = '超管'

const AppSidebar: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const { openKeys, setOpenKeys, updateForNavigation } = useSidebarStore()
  const { toggleSidebar, state: sidebarState } = useSidebar()
  const { theme, setTheme } = useTheme()
  const isDark = theme !== 'light'

  const { useServers } = useServerQueries()
  const serversQuery = useServers()
  const servers = serversQuery.data || []
  const selfCheckHealth = useSelfCheckHealth()
  const selfCheckIssueCount = selfCheckHealth.issueCount
  const selfCheckIssueCritical = selfCheckHealth.status === 'critical'

  const currentUserQuery = useCurrentUser()
  const currentUser = currentUserQuery.data
  const isOwner = currentUser?.role === UserRole.OWNER

  useEffect(() => {
    updateForNavigation(location.pathname)
  }, [location.pathname, updateForNavigation])

  const handleLogout = async () => {
    await authApi.logout().catch(() => undefined)
    queryClient.clear()
    navigate('/login')
  }

  const isKeyOpen = (key: string) => openKeys.includes(key)
  const toggleKey = (key: string) => {
    if (openKeys.includes(key)) {
      setOpenKeys(openKeys.filter((k) => k !== key))
    } else {
      setOpenKeys([...openKeys, key])
    }
  }

  const isActive = (path: string) => location.pathname === path
  const navigateTo = (path: string) => navigate(path)

  return (
    <Sidebar collapsible="icon">
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={isActive('/')}
                  onClick={() => navigateTo('/')}
                  tooltip="系统自检"
                >
                  <ShieldCheck />
                  <span>系统自检</span>
                </SidebarMenuButton>
                {selfCheckIssueCount > 0 && (
                  <>
                    <SidebarMenuBadge
                      className={cn(
                        'text-white',
                        selfCheckIssueCritical ? 'bg-red-600' : 'bg-yellow-600'
                      )}
                    >
                      {selfCheckIssueCount}
                    </SidebarMenuBadge>
                    <span
                      className={cn(
                        'absolute right-2 top-2 hidden h-2 w-2 rounded-full group-data-[collapsible=icon]:block',
                        selfCheckIssueCritical ? 'bg-red-500' : 'bg-yellow-500'
                      )}
                    />
                  </>
                )}
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={isActive('/overview')}
                  onClick={() => navigateTo('/overview')}
                  tooltip="服务器总览"
                >
                  <LayoutDashboard />
                  <span>服务器总览</span>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <Collapsible
                open={isKeyOpen(SERVER_GROUP_KEY)}
                onOpenChange={() => toggleKey(SERVER_GROUP_KEY)}
              >
                <SidebarMenuItem>
                  <SidebarMenuButton
                    onClick={() => toggleKey(SERVER_GROUP_KEY)}
                    tooltip="服务器管理"
                  >
                    <Database />
                    <span>服务器管理</span>
                    <ChevronRight
                      className={cn(
                        'ml-auto transition-transform',
                        isKeyOpen(SERVER_GROUP_KEY) && 'rotate-90'
                      )}
                    />
                  </SidebarMenuButton>
                  <CollapsibleContent>
                    <SidebarMenuSub>
                      {servers.map((server) => (
                        <Collapsible
                          key={server.id}
                          open={isKeyOpen(server.id)}
                          onOpenChange={() => toggleKey(server.id)}
                        >
                          <SidebarMenuSubItem>
                            <SidebarMenuSubButton
                              onClick={() => toggleKey(server.id)}
                              className="cursor-pointer"
                            >
                              <ServerMenuIcon serverId={server.id} />
                              <span>{server.id}</span>
                              <ChevronRight
                                className={cn(
                                  'ml-auto h-3 w-3 transition-transform',
                                  isKeyOpen(server.id) && 'rotate-90'
                                )}
                              />
                            </SidebarMenuSubButton>
                            <CollapsibleContent>
                              <SidebarMenuSub>
                                <SidebarMenuSubItem>
                                  <SidebarMenuSubButton
                                    isActive={isActive(`/server/${server.id}`)}
                                    onClick={() => navigateTo(`/server/${server.id}`)}
                                    className="cursor-pointer"
                                  >
                                    <LayoutDashboard />
                                    <span>概览</span>
                                  </SidebarMenuSubButton>
                                </SidebarMenuSubItem>
                                <SidebarMenuSubItem>
                                  <SidebarMenuSubButton
                                    isActive={isActive(`/server/${server.id}/compose`)}
                                    onClick={() => navigateTo(`/server/${server.id}/compose`)}
                                    className="cursor-pointer"
                                  >
                                    <Settings />
                                    <span>设置</span>
                                  </SidebarMenuSubButton>
                                </SidebarMenuSubItem>
                                <SidebarMenuSubItem>
                                  <SidebarMenuSubButton
                                    isActive={isActive(`/server/${server.id}/files`)}
                                    onClick={() => navigateTo(`/server/${server.id}/files`)}
                                    className="cursor-pointer"
                                  >
                                    <Folder />
                                    <span>文件</span>
                                  </SidebarMenuSubButton>
                                </SidebarMenuSubItem>
                                <SidebarMenuSubItem>
                                  <SidebarMenuSubButton
                                    isActive={isActive(`/server/${server.id}/console`)}
                                    onClick={() => navigateTo(`/server/${server.id}/console`)}
                                    className="cursor-pointer"
                                  >
                                    <Code />
                                    <span>控制台</span>
                                  </SidebarMenuSubButton>
                                </SidebarMenuSubItem>
                                <SidebarMenuSubItem>
                                  <SidebarMenuSubButton
                                    isActive={isActive(`/server/${server.id}/world-restore`)}
                                    onClick={() => navigateTo(`/server/${server.id}/world-restore`)}
                                    className="cursor-pointer"
                                  >
                                    <MapIcon />
                                    <span>地图回档</span>
                                  </SidebarMenuSubButton>
                                </SidebarMenuSubItem>
                                <SidebarMenuSubItem>
                                  <SidebarMenuSubButton
                                    isActive={isActive(`/server/${server.id}/chunk-prune`)}
                                    onClick={() => navigateTo(`/server/${server.id}/chunk-prune`)}
                                    className="cursor-pointer"
                                  >
                                    <Eraser />
                                    <span>区块清理</span>
                                  </SidebarMenuSubButton>
                                </SidebarMenuSubItem>
                              </SidebarMenuSub>
                            </CollapsibleContent>
                          </SidebarMenuSubItem>
                        </Collapsible>
                      ))}
                      <SidebarMenuSubItem>
                        <SidebarMenuSubButton
                          isActive={isActive('/server/new')}
                          onClick={() => navigateTo('/server/new')}
                          className="cursor-pointer"
                        >
                          <Plus />
                          <span>新建</span>
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </SidebarMenuItem>
              </Collapsible>

              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={isActive('/templates')}
                  onClick={() => navigateTo('/templates')}
                  tooltip="服务器模板"
                >
                  <FileText />
                  <span>服务器模板</span>
                </SidebarMenuButton>
              </SidebarMenuItem>

              {isOwner && (
                <Collapsible
                  open={isKeyOpen(ADMIN_GROUP_KEY)}
                  onOpenChange={() => toggleKey(ADMIN_GROUP_KEY)}
                >
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      onClick={() => toggleKey(ADMIN_GROUP_KEY)}
                      tooltip="超管"
                    >
                      <Crown />
                      <span>超管</span>
                      <ChevronRight
                        className={cn(
                          'ml-auto transition-transform',
                          isKeyOpen(ADMIN_GROUP_KEY) && 'rotate-90'
                        )}
                      />
                    </SidebarMenuButton>
                    <CollapsibleContent>
                      <SidebarMenuSub>
                        <SidebarMenuSubItem>
                          <SidebarMenuSubButton
                            isActive={isActive('/admin/users')}
                            onClick={() => navigateTo('/admin/users')}
                            className="cursor-pointer"
                          >
                            <UserCog />
                            <span>用户管理</span>
                          </SidebarMenuSubButton>
                        </SidebarMenuSubItem>
                      </SidebarMenuSub>
                    </CollapsibleContent>
                  </SidebarMenuItem>
                </Collapsible>
              )}

              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={isActive('/players')}
                  onClick={() => navigateTo('/players')}
                  tooltip="玩家管理"
                >
                  <Users />
                  <span>玩家管理</span>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={isActive('/snapshots')}
                  onClick={() => navigateTo('/snapshots')}
                  tooltip="快照管理"
                >
                  <History />
                  <span>快照管理</span>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={isActive('/archives')}
                  onClick={() => navigateTo('/archives')}
                  tooltip="压缩包管理"
                >
                  <FileArchive />
                  <span>压缩包管理</span>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={isActive('/config')}
                  onClick={() => navigateTo('/config')}
                  tooltip="动态配置"
                >
                  <Settings />
                  <span>动态配置</span>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={isActive('/dns')}
                  onClick={() => navigateTo('/dns')}
                  tooltip="DNS管理"
                >
                  <Globe />
                  <span>DNS管理</span>
                </SidebarMenuButton>
              </SidebarMenuItem>

              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={isActive('/cron')}
                  onClick={() => navigateTo('/cron')}
                  tooltip="任务管理"
                >
                  <Calendar />
                  <span>任务管理</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="flex-row items-center justify-around gap-1 group-data-[collapsible=icon]:flex-col-reverse">
        <Tooltip>
          <TooltipTrigger
            className="inline-flex"
            render={
              <Button variant="ghost" size="icon-sm" onClick={toggleSidebar} />
            }
          >
            <PanelLeftIcon className="h-4 w-4" />
            <span className="sr-only">
              {sidebarState === 'expanded' ? '收起' : '展开'}
            </span>
          </TooltipTrigger>
          <TooltipContent side="right">
            {sidebarState === 'expanded' ? '收起' : '展开'}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger
            className="inline-flex"
            render={
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setTheme(isDark ? 'light' : 'dark')}
              />
            }
          >
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            <span className="sr-only">切换主题</span>
          </TooltipTrigger>
          <TooltipContent side="right">
            {isDark ? '切换到亮色主题' : '切换到深色主题'}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger
            className="inline-flex"
            render={
              <Button variant="ghost" size="icon-sm" onClick={handleLogout} />
            }
          >
            <LogOut className="h-4 w-4" />
            <span className="sr-only">退出登录</span>
          </TooltipTrigger>
          <TooltipContent side="right">退出登录</TooltipContent>
        </Tooltip>

        <DebugTool />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}

export default AppSidebar
