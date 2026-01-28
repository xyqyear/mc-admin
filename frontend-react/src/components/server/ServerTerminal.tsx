import React, { useEffect, useCallback, useMemo, forwardRef, useImperativeHandle } from 'react';
import { useXTerm } from 'react-xtermjs';
import { ITerminalOptions } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { WebSocketMessage } from '@/hooks/useServerConsoleWebSocket';

export interface ServerTerminalRef {
  clear: () => void;
  write: (data: string) => void;
  fit: () => void;
  getSize: () => { cols: number; rows: number } | null;
  onMessage: (message: WebSocketMessage) => void;
}

export interface ServerTerminalProps {
  onSendInput?: (data: string) => void;
  onReady?: (terminalRef: ServerTerminalRef) => void;
  onResize?: (cols: number, rows: number) => void;
  className?: string;
  height?: string;
}

const ServerTerminal = forwardRef<ServerTerminalRef, ServerTerminalProps>(({
  onSendInput,
  onReady,
  onResize,
  className = "h-full",
  height
}, ref) => {
  // XTerm configuration
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

  const fitAddon = terminalAddons[0] as FitAddon;

  const terminal = useXTerm({
    options: terminalOptions,
    addons: terminalAddons,
  });

  const terminalRef = terminal.ref;
  const terminalInstance = terminal.instance;

  // Handle WebSocket messages
  const handleWebSocketMessage = useCallback((message: WebSocketMessage) => {
    if (!terminalInstance) return;

    switch (message.type) {
      case 'log':
        if (message.content) {
          terminalInstance.write(message.content);
        }
        break;

      case 'error':
        if (message.message) {
          terminalInstance.write(`\x1b[31mError: ${message.message}\x1b[0m\r\n`);
        }
        break;

      case 'info':
        if (message.message) {
          terminalInstance.write(`\x1b[36mInfo: ${message.message}\x1b[0m\r\n`);
        } else if (message.content) {
          terminalInstance.write(`\x1b[36mInfo: ${message.content}\x1b[0m\r\n`);
        }
        break;
    }
  }, [terminalInstance]);

  // Handle terminal data input - send raw keystrokes directly
  const handleTerminalData = useCallback((data: string) => {
    if (onSendInput) {
      onSendInput(data);
    }
  }, [onSendInput]);

  // Exposed methods
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
    getSize: () => {
      if (terminalInstance) {
        return { cols: terminalInstance.cols, rows: terminalInstance.rows };
      }
      return null;
    },
    onMessage: handleWebSocketMessage,
  }), [terminalInstance, fitAddon, handleWebSocketMessage]);

  useImperativeHandle(ref, () => terminalMethods, [terminalMethods]);

  // Set up terminal data listener
  useEffect(() => {
    if (terminalInstance) {
      const disposable = terminalInstance.onData(handleTerminalData);
      return () => {
        disposable?.dispose();
      };
    }
  }, [terminalInstance, handleTerminalData]);

  // Configure custom key event handler for Ctrl+C and Ctrl+V browser default behavior
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

  // Auto-resize terminal using ResizeObserver for container size changes
  useEffect(() => {
    if (fitAddon && terminalInstance && terminalRef.current) {
      setTimeout(() => fitAddon.fit(), 0);

      const resizeObserver = new ResizeObserver(() => {
        fitAddon.fit();
      });

      resizeObserver.observe(terminalRef.current);
      return () => {
        resizeObserver.disconnect();
      };
    }
  }, [fitAddon, terminalInstance, terminalRef]);

  // Listen for terminal resize events and notify parent
  useEffect(() => {
    if (terminalInstance && onResize) {
      const disposable = terminalInstance.onResize(({ cols, rows }) => {
        onResize(cols, rows);
      });
      return () => {
        disposable?.dispose();
      };
    }
  }, [terminalInstance, onResize]);

  // Notify parent when component is ready
  useEffect(() => {
    if (terminalInstance && onReady) {
      onReady(terminalMethods);
    }
  }, [terminalInstance, onReady, terminalMethods]);

  return (
    <div
      ref={terminalRef as React.LegacyRef<HTMLDivElement>}
      className={className}
      style={{ overflow: 'hidden', ...(height ? { height } : {}) }}
    />
  );
});

ServerTerminal.displayName = 'ServerTerminal';

export default ServerTerminal;
