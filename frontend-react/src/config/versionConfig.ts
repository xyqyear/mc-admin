interface VersionUpdate {
  version: string
  date: string
  title: string
  description: string
  features?: string[]
  fixes?: string[]
  improvements?: string[]
}

export const versionUpdates: VersionUpdate[] = [
  {
    version: '0.1.0',
    date: '2025-09-09',
    title: '初始版本发布',
    description: 'MC Admin 首次发布，提供完整的 Minecraft 服务器管理功能。',
    features: [
      '完整的服务器生命周期管理',
      'Docker Compose 配置管理',
      '实时控制台和资源监控',
      'JWT 认证系统',
      '文件管理系统',
      '快照管理',
      '...'
    ]
  },
  {
    version: '0.1.4',
    date: '2025-09-09',
    title: '文件支持拖拽上传',
    description: '上传文件时支持拖拽上传功能，提升用户体验。',
    features: [
      '支持文件拖拽上传',
    ],
    improvements: []
  },
  {
    version: '0.1.5',
    date: '2025-09-09',
    title: '压缩包功能增强',
    description: '优化服务器文件压缩体验，增加超时保护和用户友好提示。',
    improvements: [
      '压缩包创建API超时时间延长至15分钟，支持大型服务器压缩',
      '压缩过程中添加友好提示，告知用户不要关闭窗口',
      '压缩进行时禁用窗口关闭功能，防止用户误操作',
    ]
  },
  {
    version: '0.1.6',
    date: '2025-09-09',
    title: '增加文件上传超时时间',
    description: '增加文件上传超时时间',
    features: [
      '增加文件上传的超时时间',
    ]
  },
  {
    version: '0.1.7',
    date: '2025-09-10',
    title: '添加服务器地址卡片',
    description: '添加服务器地址卡片',
    features: [
      '在服务器的概览页面添加服务器地址卡片，支持按钮复制',
    ]
  },
  {
    version: '0.1.9',
    date: '2025-09-10',
    title: '终端支持 Ctrl+C 和 Ctrl+V',
    description: '终端支持 Ctrl+C 和 Ctrl+V',
    features: [
      '终端支持 Ctrl+C 和 Ctrl+V',
    ],
    improvements: [
      '修复服务器地址卡片显示错误问题'
    ]
  },
  {
    version: '0.2.0',
    date: '2025-09-18',
    title: '定时任务系统重大更新',
    description: 'MC Admin 迎来重大功能更新，新增完整的定时任务管理系统，支持自动备份、服务器重启等定时操作。',
    features: [
      '全新定时任务管理系统，支持 Cron 表达式定义定时任务',
      '定时任务管理页面，可创建、编辑、删除和监控定时任务',
      '内置备份任务和服务器重启任务模板',
      '定时任务执行历史和状态监控',
      '可视化 Cron 表达式构建器',
      '定时任务下次执行时间预览',
      'JSON Schema 表单组件，支持动态表单生成',
      '侧边栏导航增加定时任务入口',
    ],
    improvements: [
      '测试结构重新组织，按功能模块分类',
      '新增大量定时任务相关测试用例',
      '快照管理测试完善和优化',
      '存档管理测试结构优化',
      'API 结构优化，新增配置和定时任务 API',
      '项目文档更新，增加 README 截图和说明'
    ],
    fixes: [
      '快照管理功能稳定性提升',
      '数据库迁移文件清理和优化',
      '构建脚本优化'
    ]
  },
  {
    version: '0.2.1',
    date: '2025-09-18',
    title: '备份任务集成 Uptime Kuma 监控',
    description: '定时备份任务新增 Uptime Kuma 监控集成，可以自动向 Uptime Kuma 推送备份任务的执行状态和运行时间。',
    features: [
      '备份任务支持 Uptime Kuma 推送监控',
    ]
  },
  {
    version: '0.2.2',
    date: '2025-09-18',
    title: '数据库时间显示时区错误修复',
    description: '修复数据库时间显示时区错误问题，确保所有前端显示时间均为本地时间。',
    fixes: [
      '修复数据库时间显示时区错误问题'
    ]
  },
  {
    version: '0.2.3',
    date: '2025-09-18',
    title: '定时任务管理功能增强',
    description: '定时任务系统新增冲突检测和日志查看功能，提升任务管理体验。',
    features: [
      '定时任务创建时增加重启-备份时间冲突警告',
      '定时任务详情页新增日志查看功能'
    ]
  },
  {
    version: '0.2.4',
    date: '2025-09-18',
    title: '服务器重启管理功能优化',
    description: '自动添加和删除服务器重启计划并在服务器概览页显示重启计划状态。',
    features: [
      '创建服务器时自动添加默认重启计划',
      '删除服务器时自动删除相关重启计划',
      '服务器概览页显示重启计划状态和下次重启时间'
    ]
  },
  {
    version: '0.2.5',
    date: '2025-09-22',
    title: '文件下载进度系统',
    description: '全新的文件下载体验，支持实时进度显示和下载任务管理。',
    features: [
      '下载进度实时显示，支持速度和剩余时间计算',
      'Sidebar 底部下载任务管理容器',
      '下载任务支持取消操作',
      '服务器文件和 Archive 文件统一下载体验'
    ],
    improvements: [
      '重构下载逻辑，消除重复代码',
      '统一的下载工具函数和状态管理',
      '增加了下载的超时时间'
    ]
  }
]

export function compareVersions(a: string, b: string): number {
  const parseVersion = (version: string) => 
    version.split('.').map(num => parseInt(num, 10))
  
  const versionA = parseVersion(a)
  const versionB = parseVersion(b)
  
  for (let i = 0; i < Math.max(versionA.length, versionB.length); i++) {
    const numA = versionA[i] || 0
    const numB = versionB[i] || 0
    
    if (numA < numB) return -1
    if (numA > numB) return 1
  }
  
  return 0
}

// 自动获取版本配置中的最大版本作为当前版本
export const currentVersion = versionUpdates.length > 0 
  ? versionUpdates.reduce((latest, update) => 
      compareVersions(update.version, latest.version) > 0 ? update : latest
    ).version
  : '0.1.0'