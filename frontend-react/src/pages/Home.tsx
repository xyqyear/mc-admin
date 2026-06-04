import { useNavigate } from 'react-router'
import {
  Server,
  Plus,
  Users,
  CloudDownload,
  FileArchive,
  Globe,
  Clock,
  Settings,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'

const featureCards = [
  {
    title: '服务器管理',
    description: '管理现有服务器，查看详细信息和性能指标',
    icon: Server,
    path: '/overview',
    iconClass: 'text-purple-600',
    bgClass: 'bg-purple-100',
  },
  {
    title: '创建服务器',
    description: '快速创建和配置新的 Minecraft 服务器实例',
    icon: Plus,
    path: '/server/new',
    iconClass: 'text-green-600',
    bgClass: 'bg-green-100',
  },
  {
    title: '玩家管理',
    description: '查看玩家信息、在线状态和游戏记录',
    icon: Users,
    path: '/players',
    iconClass: 'text-cyan-600',
    bgClass: 'bg-cyan-100',
  },
  {
    title: '快照管理',
    description: '创建和管理服务器快照，支持数据备份和恢复操作',
    icon: CloudDownload,
    path: '/snapshots',
    iconClass: 'text-orange-600',
    bgClass: 'bg-orange-100',
  },
  {
    title: '归档管理',
    description: '管理服务器归档文件，支持上传和删除服务器压缩包',
    icon: FileArchive,
    path: '/archives',
    iconClass: 'text-pink-600',
    bgClass: 'bg-pink-100',
  },
  {
    title: 'DNS管理',
    description: '管理域名解析记录，配置服务器地址映射',
    icon: Globe,
    path: '/dns',
    iconClass: 'text-blue-600',
    bgClass: 'bg-blue-100',
  },
  {
    title: '任务管理',
    description: '配置定时任务，自动执行备份和重启等操作',
    icon: Clock,
    path: '/cron',
    iconClass: 'text-amber-600',
    bgClass: 'bg-amber-100',
  },
  {
    title: '动态配置',
    description: '管理系统配置参数，自定义平台行为',
    icon: Settings,
    path: '/config',
    iconClass: 'text-gray-600',
    bgClass: 'bg-gray-100',
  },
]

const Home = () => {
  const navigate = useNavigate()

  return (
    <div className="space-y-4">
      <div className="text-center space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">
          MC Admin 管理系统
        </h1>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
          专业的 Minecraft 服务器管理平台，提供完整的服务器生命周期管理和监控功能
        </p>
      </div>

      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-center mb-8">核心功能</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {featureCards.map((card) => (
            <Card
              key={card.path}
              className="h-full cursor-pointer transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5"
              onClick={() => navigate(card.path)}
            >
              <CardContent className="pt-8 pb-8">
                <div className="text-center space-y-4">
                  <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full ${card.bgClass}`}>
                    <card.icon className={`h-7 w-7 ${card.iconClass}`} />
                  </div>
                  <h4 className="text-base font-semibold">{card.title}</h4>
                  <p className="text-muted-foreground text-sm leading-relaxed">
                    {card.description}
                  </p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}

export default Home
