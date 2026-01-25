import React, { useEffect, useRef, useCallback, useMemo, forwardRef, useImperativeHandle } from 'react';
import { useXTerm } from 'react-xtermjs';
import { ITerminalOptions } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { WebSocketMessage } from '@/hooks/useServerConsoleWebSocket';
import { commandHistory } from '@/utils/commandHistoryUtils';

export interface ServerTerminalRef {
  clear: () => void;
  write: (data: string) => void;
  fit: () => void;
  onMessage: (message: WebSocketMessage) => void;
}

export interface ServerTerminalProps {
  serverId: string;
  onCommand?: (command: string) => void;
  onReady?: (terminalRef: ServerTerminalRef) => void;
  className?: string;
  height?: string;
}

const ServerTerminal = forwardRef<ServerTerminalRef, ServerTerminalProps>(({
  serverId,
  onCommand,
  onReady,
  className = "h-full",
  height
}, ref) => {
  // 使用 ref 存储当前命令，避免不必要的重渲染和依赖问题
  const currentCommandRef = useRef('');
  // Command history navigation state
  const historyIndexRef = useRef(-1);  // -1 means not navigating history
  const savedInputRef = useRef('');     // Save current input when starting history navigation

  // XTerm 配置 - 使用useMemo来避免每次渲染重新创建
  const terminalOptions: ITerminalOptions = useMemo(() => ({
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
    scrollback: 10000,
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

  // Replace current line with new text (for history navigation)
  const replaceCurrentLine = useCallback((newText: string) => {
    if (!terminalInstance) return;

    // Clear current line
    const currentWidth = calculateDisplayWidth(currentCommandRef.current);
    if (currentWidth > 0) {
      terminalInstance.write('\r' + ' '.repeat(currentWidth) + '\r');
    }

    // Write new text
    currentCommandRef.current = newText;
    terminalInstance.write(newText);
  }, [terminalInstance, calculateDisplayWidth]);

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
    // Handle arrow keys (escape sequences)
    if (data.startsWith('\x1b[')) {
      const code = data.slice(2);

      if (code === 'A') {  // Up arrow
        const history = commandHistory.getHistory(serverId);
        if (history.length === 0) return;

        // Save current input when starting navigation
        if (historyIndexRef.current === -1) {
          savedInputRef.current = currentCommandRef.current;
          historyIndexRef.current = history.length;
        }

        if (historyIndexRef.current > 0) {
          historyIndexRef.current--;
          replaceCurrentLine(history[historyIndexRef.current]);
        }
        return;
      }

      if (code === 'B') {  // Down arrow
        const history = commandHistory.getHistory(serverId);
        if (historyIndexRef.current === -1) return;

        historyIndexRef.current++;

        if (historyIndexRef.current >= history.length) {
          // Restore saved input
          historyIndexRef.current = -1;
          replaceCurrentLine(savedInputRef.current);
          savedInputRef.current = '';
        } else {
          replaceCurrentLine(history[historyIndexRef.current]);
        }
        return;
      }

      // Ignore other escape sequences (left/right arrows, etc.)
      return;
    }

    // 处理回车键
    if (data === '\r') {
      if (currentCommandRef.current.trim()) {
        const command = currentCommandRef.current.trim();

        // Save to history
        commandHistory.addCommand(serverId, command);

        // 发送命令
        if (onCommand) {
          onCommand(command);
        }
        currentCommandRef.current = '';
      }

      // Reset history navigation
      historyIndexRef.current = -1;
      savedInputRef.current = '';

      if (terminalInstance) {
        terminalInstance.write('\r');
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
      currentCommandRef.current = '';
      // Reset history navigation
      historyIndexRef.current = -1;
      savedInputRef.current = '';
      return;
    }

    // 处理普通字符
    if (data >= ' ' || data === '\t') {
      // Reset history navigation when typing
      historyIndexRef.current = -1;
      savedInputRef.current = '';

      currentCommandRef.current += data; // 直接操作 ref
      if (terminalInstance) {
        terminalInstance.write(data);
      }
    }
  }, [terminalInstance, calculateDisplayWidth, onCommand, serverId, replaceCurrentLine]);

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

  // 配置自定义键盘事件处理器，让Ctrl+C和Ctrl+V使用浏览器默认行为
  useEffect(() => {
    if (terminalInstance) {
      terminalInstance.attachCustomKeyEventHandler((event) => {
        if (event.ctrlKey && (event.key === 'c' || event.key === 'v')) {
          return false;
        }
        return true;
      });
    }
  }, [terminalInstance]);

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