import type { ServerStatus, ServerType } from '@/types/ServerInfo'

// 状态相关工具函数
export const serverStatusUtils = {
  // 获取状态对应的颜色
  getStatusColor: (status: ServerStatus): string => {
    switch (status) {
      case 'HEALTHY': return 'success'
      case 'RUNNING': return 'processing'
      case 'STARTING': return 'warning'
      case 'CREATED': return 'default'
      case 'EXISTS': return 'warning'
      case 'REMOVED': return 'error'
      default: return 'default'
    }
  },
  
  // 获取状态对应的图标
  getStatusIcon: (status: ServerStatus): string => {
    switch (status) {
      case 'HEALTHY': return 'CheckCircleOutlined'
      case 'RUNNING': return 'PlayCircleOutlined'
      case 'STARTING': return 'LoadingOutlined'
      case 'CREATED': return 'PauseCircleOutlined'
      case 'EXISTS': return 'ExclamationCircleOutlined'
      case 'REMOVED': return 'MinusCircleOutlined'
      default: return 'ExclamationCircleOutlined'
    }
  },
  
  // 判断服务器是否可以执行某个操作
  isOperationAvailable: (operation: string, status: ServerStatus): boolean => {
    switch (operation) {
      case 'start':
        return ['CREATED', 'EXISTS'].includes(status)
      case 'stop':
        return ['RUNNING', 'HEALTHY', 'STARTING'].includes(status)
      case 'restart':
        return ['RUNNING', 'HEALTHY'].includes(status)
      case 'remove':
        return !['STARTING'].includes(status)
      default:
        return false
    }
  },
  
  // 判断是否为运行状态
  isRunning: (status: ServerStatus): boolean => {
    return ['RUNNING', 'STARTING', 'HEALTHY'].includes(status)
  },
  
  // 判断是否为健康状态
  isHealthy: (status: ServerStatus): boolean => {
    return status === 'HEALTHY'
  }
}

// 服务器类型工具函数
export const serverTypeUtils = {
  // 获取服务器类型对应的颜色
  getTypeColor: (type: ServerType): string => {
    switch (type) {
      case 'VANILLA': return 'green'
      case 'PAPER': return 'blue'
      case 'FORGE': return 'orange'
      case 'FABRIC': return 'purple'
      case 'SPIGOT': return 'cyan'
      case 'BUKKIT': return 'gold'
      case 'NEOFORGE': return 'red'
      case 'CUSTOM': return 'default'
      default: return 'default'
    }
  }
}

// 数据格式化工具函数
export const formatUtils = {
  // 格式化字节数为可读字符串
  formatBytes: (bytes: number, decimals: number = 1): string => {
    if (bytes === 0) return '0 B'
    
    const k = 1024
    const dm = decimals < 0 ? 0 : decimals
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`
  },
  
  // 格式化百分比
  formatPercentage: (value: number, decimals: number = 1): string => {
    return `${value.toFixed(decimals)}%`
  },
  
  // 格式化内存 (字节转MB)
  formatMemoryMB: (bytes: number): string => {
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  },
  
  // 格式化内存 (字节转GB)
  formatMemoryGB: (bytes: number): string => {
    return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
  },
  
  // 格式化运行时间
  formatUptime: (seconds: number): string => {
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    
    if (days > 0) {
      return `${days}天 ${hours}小时`
    } else if (hours > 0) {
      return `${hours}小时 ${minutes}分钟`
    } else {
      return `${minutes}分钟`
    }
  }
}

// 服务器地址工具函数
export const serverAddressUtils = {
  // 获取服务器连接地址
  getConnectionAddress: (port: number, host: string = 'localhost'): string => {
    return `${host}:${port}`
  },
  
  // 复制服务器地址到剪贴板
  copyServerAddress: async (port: number, host: string = 'localhost'): Promise<void> => {
    const address = serverAddressUtils.getConnectionAddress(port, host)
    await navigator.clipboard.writeText(address)
  }
}
