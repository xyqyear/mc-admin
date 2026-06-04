import { useEffect, useCallback, useMemo, forwardRef, useImperativeHandle, useRef } from 'react';
import { Terminal, type IDisposable, type ITerminalOptions } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import type { WebSocketMessage } from '@/hooks/useServerConsoleWebSocket';
import '@xterm/xterm/css/xterm.css';

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
  const terminalElementRef = useRef<HTMLDivElement | null>(null);
  const terminalInstanceRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const onSendInputRef = useRef(onSendInput);
  const onReadyRef = useRef(onReady);
  const onResizeRef = useRef(onResize);

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

  useEffect(() => {
    onSendInputRef.current = onSendInput;
  }, [onSendInput]);

  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);

  useEffect(() => {
    onResizeRef.current = onResize;
  }, [onResize]);

  const handleWebSocketMessage = useCallback((message: WebSocketMessage) => {
    const terminalInstance = terminalInstanceRef.current;
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
  }, []);

  const terminalMethods = useMemo(() => ({
    clear: () => {
      const terminalInstance = terminalInstanceRef.current;
      if (terminalInstance) {
        terminalInstance.clear();
      }
    },
    write: (data: string) => {
      const terminalInstance = terminalInstanceRef.current;
      if (terminalInstance) {
        terminalInstance.write(data);
      }
    },
    fit: () => {
      const fitAddon = fitAddonRef.current;
      if (fitAddon) {
        fitAddon.fit();
      }
    },
    getSize: () => {
      const terminalInstance = terminalInstanceRef.current;
      if (terminalInstance) {
        return { cols: terminalInstance.cols, rows: terminalInstance.rows };
      }
      return null;
    },
    onMessage: handleWebSocketMessage,
  }), [handleWebSocketMessage]);

  useImperativeHandle(ref, () => terminalMethods, [terminalMethods]);

  useEffect(() => {
    const element = terminalElementRef.current;
    if (!element) return;

    const terminalInstance = new Terminal(terminalOptions);
    const fitAddon = new FitAddon();
    const disposables: IDisposable[] = [];

    terminalInstance.loadAddon(fitAddon);
    terminalInstance.loadAddon(new WebLinksAddon());
    terminalInstance.open(element);
    terminalInstance.attachCustomKeyEventHandler((event) => {
      if (event.ctrlKey && (event.key === 'c' || event.key === 'v')) {
        return false;
      }
      return true;
    });

    terminalInstanceRef.current = terminalInstance;
    fitAddonRef.current = fitAddon;

    disposables.push(
      terminalInstance.onData((data) => {
        onSendInputRef.current?.(data);
      }),
    );
    disposables.push(
      terminalInstance.onResize(({ cols, rows }) => {
        onResizeRef.current?.(cols, rows);
      }),
    );

    const fitTimer = window.setTimeout(() => fitAddon.fit(), 0);
    const resizeObserver = new ResizeObserver(() => fitAddon.fit());
    resizeObserver.observe(element);

    onReadyRef.current?.(terminalMethods);

    return () => {
      window.clearTimeout(fitTimer);
      resizeObserver.disconnect();
      for (const disposable of disposables) {
        disposable.dispose();
      }
      terminalInstance.dispose();
      terminalInstanceRef.current = null;
      fitAddonRef.current = null;
    }
  }, [terminalOptions, terminalMethods]);

  return (
    <div
      ref={terminalElementRef}
      className={className}
      style={{ overflow: 'hidden', ...(height ? { height } : {}) }}
    />
  );
});

ServerTerminal.displayName = 'ServerTerminal';

export default ServerTerminal;
