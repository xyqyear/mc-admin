// Console wrapper that no-ops in production builds; calls are tree-shaken when DEV is false.
class DevLogger {
  log(...args: any[]): void {
    if (import.meta.env.DEV) {
      console.log(...args);
    }
  }

  error(...args: any[]): void {
    if (import.meta.env.DEV) {
      console.error(...args);
    }
  }

  warn(...args: any[]): void {
    if (import.meta.env.DEV) {
      console.warn(...args);
    }
  }

  debug(...args: any[]): void {
    if (import.meta.env.DEV) {
      console.debug(...args);
    }
  }

  info(...args: any[]): void {
    if (import.meta.env.DEV) {
      console.info(...args);
    }
  }

  table(data: any): void {
    if (import.meta.env.DEV) {
      console.table(data);
    }
  }

  group(label?: string): void {
    if (import.meta.env.DEV) {
      console.group(label);
    }
  }

  groupCollapsed(label?: string): void {
    if (import.meta.env.DEV) {
      console.groupCollapsed(label);
    }
  }

  groupEnd(): void {
    if (import.meta.env.DEV) {
      console.groupEnd();
    }
  }

  time(label?: string): void {
    if (import.meta.env.DEV) {
      console.time(label);
    }
  }

  timeEnd(label?: string): void {
    if (import.meta.env.DEV) {
      console.timeEnd(label);
    }
  }

  timeLog(label?: string, ...data: any[]): void {
    if (import.meta.env.DEV) {
      console.timeLog(label, ...data);
    }
  }
}

export const log = new DevLogger();
export default log;
