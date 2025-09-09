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