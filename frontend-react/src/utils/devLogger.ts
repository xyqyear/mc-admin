/**
 * 开发环境日志工具
 * 只在开发环境下输出日志，生产环境会被 Vite 的 tree-shaking 移除
 */

class DevLogger {
  /**
   * 输出普通日志信息
   */
  log(...args: any[]): void {
    if (import.meta.env.DEV) {
      console.log(...args)
    }
  }

  /**
   * 输出错误日志信息
   */
  error(...args: any[]): void {
    if (import.meta.env.DEV) {
      console.error(...args)
    }
  }

  /**
   * 输出警告日志信息
   */
  warn(...args: any[]): void {
    if (import.meta.env.DEV) {
      console.warn(...args)
    }
  }

  /**
   * 输出调试日志信息
   */
  debug(...args: any[]): void {
    if (import.meta.env.DEV) {
      console.debug(...args)
    }
  }

  /**
   * 输出信息日志
   */
  info(...args: any[]): void {
    if (import.meta.env.DEV) {
      console.info(...args)
    }
  }

  /**
   * 输出表格数据
   */
  table(data: any): void {
    if (import.meta.env.DEV) {
      console.table(data)
    }
  }

  /**
   * 分组开始
   */
  group(label?: string): void {
    if (import.meta.env.DEV) {
      console.group(label)
    }
  }

  /**
   * 折叠分组开始
   */
  groupCollapsed(label?: string): void {
    if (import.meta.env.DEV) {
      console.groupCollapsed(label)
    }
  }

  /**
   * 分组结束
   */
  groupEnd(): void {
    if (import.meta.env.DEV) {
      console.groupEnd()
    }
  }

  /**
   * 计时开始
   */
  time(label?: string): void {
    if (import.meta.env.DEV) {
      console.time(label)
    }
  }

  /**
   * 计时结束
   */
  timeEnd(label?: string): void {
    if (import.meta.env.DEV) {
      console.timeEnd(label)
    }
  }

  /**
   * 输出计时日志
   */
  timeLog(label?: string, ...data: any[]): void {
    if (import.meta.env.DEV) {
      console.timeLog(label, ...data)
    }
  }
}

// 导出单例实例
export const log = new DevLogger()
export default log