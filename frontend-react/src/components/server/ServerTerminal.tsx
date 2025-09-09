import React, { useEffect, useRef, useCallback, useMemo, forwardRef, useImperativeHandle } from 'react';
import { useXTerm } from 'react-xtermjs';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { WebSocketMessage } from '@/hooks/useServerConsoleWebSocket';

export interface ServerTerminalRef {
  clear: () => void;
  write: (data: string) => void;
  fit: () => void;
  onMessage: (message: WebSocketMessage) => void;
}

export interface ServerTerminalProps {
  onCommand?: (command: string) => void;
  onReady?: (terminalRef: ServerTerminalRef) => void;
  className?: string;
  height?: string;
}

const ServerTerminal = forwardRef<ServerTerminalRef, ServerTerminalProps>(({
  onCommand,
  onReady,
  className = "h-full",
  height
}, ref) => {
  // 使用 ref 存储当前命令，避免不必要的重渲染和依赖问题
  const currentCommandRef = useRef('');

  // XTerm 配置 - 使用useMemo来避免每次渲染重新创建
  const terminalOptions = useMemo(() => ({
    theme: {
      background: '#000000',
      foreground: '#ffffff',
      cursor: '#ffffff',
    },
    fontFamily: 'Consolas, "Courier New", monospace',
    fontSize: 14,
    cursorBlink: true,
    convertEol: true,
    disableStdin: false,
  }), []);

  const terminalAddons = useMemo(() => [new FitAddon(), new WebLinksAddon()], []);

  // 获取FitAddon引用
  const fitAddon = terminalAddons[0] as FitAddon;

  // 使用 useXTerm 钩子
  const terminal = useXTerm({
    options: terminalOptions,
    addons: terminalAddons,
  });

  const terminalRef = terminal.ref;
  const terminalInstance = terminal.instance;

  // 计算显示宽度（用于ESC键清除当前行）
  const calculateDisplayWidth = useCallback((text: string): number => {
    let width = 0;
    for (const char of text) {
      if (char === '\t') {
        width += 7;
      } else {
        width += 1;
      }
    }
    return width;
  }, []);

  // 重新写入当前命令的辅助函数
  const rewriteCurrentCommand = useCallback(() => {
    if (terminalInstance && currentCommandRef.current) {
      terminalInstance.write(currentCommandRef.current);
    }
  }, [terminalInstance]);

  // 处理WebSocket消息
  const handleWebSocketMessage = useCallback((message: WebSocketMessage) => {
    if (!terminalInstance) return;

    switch (message.type) {
      case 'log':
        if (message.content) {
          terminalInstance.write(message.content);
          // 重新写入当前命令
          rewriteCurrentCommand();
        }
        break;

      case 'logs_refreshed':
        if (message.content !== undefined) {
          terminalInstance.write(message.content);
          // 重新写入当前命令
          rewriteCurrentCommand();
        }
        break;

      case 'error':
        if (message.message) {
          terminalInstance.write(`\x1b[31mError: ${message.message}\x1b[0m\r\n`);
          // 错误消息后也重新写入当前命令
          rewriteCurrentCommand();
        }
        break;

      case 'info':
        if (message.message) {
          terminalInstance.write(`\x1b[36mInfo: ${message.message}\x1b[0m\r\n`);
          // 信息消息后也重新写入当前命令
          rewriteCurrentCommand();
        }
        break;
    }
  }, [terminalInstance, rewriteCurrentCommand]);

  // 处理终端数据输入
  const handleTerminalData = useCallback((data: string) => {
    // 处理回车键
    if (data === '\r') {
      if (currentCommandRef.current.trim()) {
        // 发送命令
        if (onCommand) {
          onCommand(currentCommandRef.current.trim());
        }
        currentCommandRef.current = ''; // 直接操作 ref
      }
      if (terminalInstance) {
        terminalInstance.write('\r\n');
      }
      return;
    }

    // 处理退格键
    if (data === '\x7f') {
      if (currentCommandRef.current.length > 0) {
        currentCommandRef.current = currentCommandRef.current.slice(0, -1); // 直接操作 ref
        if (terminalInstance) {
          terminalInstance.write('\b \b');
        }
      }
      return;
    }

    // 处理 ESC
    if (data === '\x1b') {
      if (currentCommandRef.current.length > 0) {
        const clearLine = '\r' + ' '.repeat(calculateDisplayWidth(currentCommandRef.current)) + '\r';
        if (terminalInstance) {
          terminalInstance.write(clearLine);
        }
      }
      currentCommandRef.current = ''; // 直接操作 ref
      return;
    }

    // 处理普通字符
    if (data >= ' ' || data === '\t') {
      currentCommandRef.current += data; // 直接操作 ref
      if (terminalInstance) {
        terminalInstance.write(data);
      }
    }
  }, [terminalInstance, calculateDisplayWidth, onCommand]);

  // 暴露的方法
  const terminalMethods = useMemo(() => ({
    clear: () => {
      if (terminalInstance) {
        terminalInstance.clear();
      }
    },
    write: (data: string) => {
      if (terminalInstance) {
        terminalInstance.write(data);
      }
    },
    fit: () => {
      if (fitAddon) {
        fitAddon.fit();
      }
    },
    onMessage: handleWebSocketMessage,
  }), [terminalInstance, fitAddon, handleWebSocketMessage]);

  // 使用 useImperativeHandle 暴露方法给父组件
  useImperativeHandle(ref, () => terminalMethods, [terminalMethods]);

  // 设置终端数据监听器
  useEffect(() => {
    if (terminalInstance) {
      const disposable = terminalInstance.onData(handleTerminalData);
      return () => {
        disposable?.dispose();
      };
    }
  }, [terminalInstance, handleTerminalData]);

  // 自动调整终端大小
  useEffect(() => {
    if (fitAddon && terminalInstance) {
      setTimeout(() => fitAddon.fit(), 0);

      const handleResize = () => {
        fitAddon.fit();
      };

      window.addEventListener('resize', handleResize);
      return () => {
        window.removeEventListener('resize', handleResize);
      };
    }
  }, [fitAddon, terminalInstance]);

  // 当组件就绪时通知父组件
  useEffect(() => {
    if (terminalInstance && onReady) {
      onReady(terminalMethods);
    }
  }, [terminalInstance, onReady, terminalMethods]);

  // 重置状态
  useEffect(() => {
    currentCommandRef.current = '';
  }, []);

  return (
    <div
      ref={terminalRef as React.LegacyRef<HTMLDivElement>}
      className={className}
      style={height ? { height } : undefined}
    />
  );
});

ServerTerminal.displayName = 'ServerTerminal';

export default ServerTerminal;