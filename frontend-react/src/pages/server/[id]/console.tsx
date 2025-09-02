import React, { useState, useRef, useEffect } from 'react'
import { 
  Card, 
  Input, 
  Button, 
  Typography, 
  Alert,
  Space,
  Spin,
  Switch
} from 'antd'
import { 
  SendOutlined
} from '@ant-design/icons'
import { useParams } from 'react-router-dom'
import { useServerDetailQueries } from '@/hooks/queries/useServerDetailQueries'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import { useToken } from '@/stores/useTokenStore'
import { log } from '@/utils/devLogger'

const { Title } = Typography
const { TextArea } = Input

// WebSocket消息类型
interface WebSocketMessage {
  type: 'log' | 'command_result' | 'error' | 'info' | 'filter_updated' | 'logs_refreshed'
  content?: string
  command?: string
  result?: string
  message?: string
  filter_rcon?: boolean
}

const ServerConsole: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const token = useToken()
  
  // 使用数据管理系统
  const { useServerDetailData } = useServerDetailQueries(id || '')
  
  const {
    serverInfo,
    status,
    isLoading,
    isError,
    error,
    hasServerInfo,
  } = useServerDetailData()
  
  // 本地状态
  const [logs, setLogs] = useState<string>('')
  const [command, setCommand] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [filterRcon, setFilterRcon] = useState(true) // 默认开启RCON过滤
  const [autoScroll, setAutoScroll] = useState(true) // 自动滚动开关
  
  // Refs
  const wsRef = useRef<WebSocket | null>(null)
  const logsRef = useRef<any>(null) // 使用any类型避免TypeScript错误
  
  // 发送过滤设置到后端的函数
  const sendFilterUpdate = (newFilterRcon: boolean) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'set_filter',
        filter_rcon: newFilterRcon
      }))
    }
  }
  
  // 请求刷新日志的函数
  const requestLogRefresh = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'refresh_logs'
      }))
    }
  }
  
  // WebSocket连接
  const connectWebSocket = () => {
    if (!id || !token) {
      log.log('Cannot connect WebSocket: missing id or token', { id, token: !!token })
      return
    }
    
    log.log('Starting WebSocket connection...')
    setIsConnecting(true)
    
    // Get the API base URL from the same configuration as HTTP requests
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:5678/api"
    const protocol = apiBaseUrl.startsWith('https:') ? 'wss:' : 'ws:'
    const host = apiBaseUrl.replace(/^https?:\/\//, '').replace('/api', '')
    const wsUrl = `${protocol}//${host}/api/servers/${id}/console?token=${encodeURIComponent(token)}`
    log.log('WebSocket URL:', wsUrl)
    log.log('API Base URL:', apiBaseUrl)
    
    try {
      wsRef.current = new WebSocket(wsUrl)
      log.log('WebSocket object created')
      
      wsRef.current.onopen = () => {
        log.log('WebSocket onopen event fired')
        setIsConnected(true)
        setIsConnecting(false)
        log.log('WebSocket connected to server console, state updated')
        
        // Send initial filter setting to backend
        setTimeout(() => {
          sendFilterUpdate(filterRcon)
        }, 100)
      }
      
      wsRef.current.onmessage = (event) => {
        log.log('WebSocket message received:', event.data)
        
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          log.log('Parsed message:', message)
          
          switch (message.type) {
            case 'log':
              if (message.content) {
                log.log('Adding log content to display')
                // 后端已经处理了过滤，直接添加到显示
                setLogs(prev => {
                  const newLogs = prev + message.content
                  log.log('New logs length:', newLogs.length)
                  return newLogs
                })
              }
              break
              
            case 'logs_refreshed':
              // 刷新日志时替换整个日志内容
              if (message.content !== undefined) {
                log.log('Refreshing logs with filtered content')
                setLogs(message.content)
                setAutoScroll(true) // 刷新后自动滚动到底部
              }
              break
              
            case 'filter_updated':
              // 过滤器更新确认
              if (message.filter_rcon !== undefined) {
                log.log('Filter updated confirmation received:', message.filter_rcon)
              }
              break
              
            case 'command_result':
              if (message.command && message.result) {
                const commandLog = `> ${message.command}\n${message.result}\n`
                setLogs(prev => prev + commandLog)
                setAutoScroll(true)
              }
              break
              
            case 'error':
              if (message.message) {
                setLogs(prev => prev + `[ERROR] ${message.message}\n`)
              }
              break
              
            case 'info':
              if (message.message) {
                setLogs(prev => prev + `[INFO] ${message.message}\n`)
              }
              break
          }
        } catch (e) {
          log.error('Failed to parse WebSocket message:', e)
        }
      }
      
      wsRef.current.onclose = (event) => {
        setIsConnected(false)
        setIsConnecting(false)
        log.log('WebSocket disconnected from server console', { code: event.code, reason: event.reason, wasClean: event.wasClean })
      }
      
      wsRef.current.onerror = (error) => {
        setIsConnecting(false)
        log.error('WebSocket error:', error)
        log.log('WebSocket state when error occurred:', wsRef.current?.readyState)
      }
      
    } catch (error) {
      setIsConnecting(false)
      log.error('Failed to create WebSocket connection:', error)
    }
  }
  
  // 断开WebSocket连接
  const disconnectWebSocket = () => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }
  
  // 发送命令
  const sendCommand = () => {
    if (!command.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    
    try {
      wsRef.current.send(JSON.stringify({
        type: 'command',
        command: command.trim()
      }))
      setCommand('')
    } catch (error) {
      log.error('Failed to send command:', error)
    }
  }
  
  
  // 处理滚动
  const handleScroll = () => {
    if ((logsRef.current as any)?.resizableTextArea?.textArea) {
      // Ant Design TextArea 实际的 DOM 元素在 resizableTextArea.textArea 中
      const textArea = (logsRef.current as any).resizableTextArea.textArea
      const { scrollTop, scrollHeight, clientHeight } = textArea
      
      // 如果用户滚动到接近底部(容差10px)，则自动开启自动滚动
      // 否则，关闭自动滚动，让用户查看历史日志
      const isAtBottom = scrollTop + clientHeight >= scrollHeight - 10
      if (isAtBottom && !autoScroll) {
        setAutoScroll(true)
        log.log('Auto scroll enabled - user scrolled to bottom')
      } else if (!isAtBottom && autoScroll) {
        setAutoScroll(false)
        log.log('Auto scroll disabled - user scrolled away from bottom')
      }
    }
  }
  
  // 组件挂载时连接WebSocket
  useEffect(() => {
    log.log('Console useEffect triggered:', { id, hasServerInfo, token: !!token, isConnecting, isConnected })
    
    // 只有在有必要信息且未连接时才尝试连接
    if (id && token && hasServerInfo && !isConnecting && !isConnected) {
      log.log('Attempting WebSocket connection...')
      connectWebSocket()
    }
    
    return () => {
      disconnectWebSocket()
    }
  }, [id, hasServerInfo, token])

  // 当过滤开关变化时，发送设置到后端并请求刷新日志
  useEffect(() => {
    if (isConnected) {
      log.log('Filter setting changed, updating backend and refreshing logs', { filterRcon })
      sendFilterUpdate(filterRcon)
      // 短暂延迟后请求刷新，确保后端已处理过滤设置
      setTimeout(() => {
        requestLogRefresh()
      }, 100)
    }
  }, [filterRcon, isConnected])

  // 当日志内容更新时，如果应该自动滚动，则滚动到底部
  useEffect(() => {
    if (logs && autoScroll && logsRef.current && (logsRef.current as any).resizableTextArea?.textArea) {
      setTimeout(() => {
        if (logsRef.current && (logsRef.current as any).resizableTextArea?.textArea) {
          const textArea = (logsRef.current as any).resizableTextArea.textArea
          textArea.scrollTop = textArea.scrollHeight
          log.log('Auto scrolled to bottom due to logs update or autoScroll enabled')
        }
      }, 10)
    }
  }, [logs, autoScroll])
  
  // 处理键盘事件
  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendCommand()
    }
  }
  
  // 如果没有服务器ID
  if (!id) {
    return (
      <Alert
        message="错误"
        description="未提供服务器ID"
        type="error"
        showIcon
      />
    )
  }

  // 如果没有认证令牌
  if (!token) {
    return (
      <Alert
        message="认证错误"
        description="您需要登录才能访问服务器控制台"
        type="error"
        showIcon
      />
    )
  }
  
  // 加载状态
  if (isLoading || !hasServerInfo || !serverInfo) {
    return <LoadingSpinner height="16rem" tip="加载服务器信息中..." />
  }
  
  // 错误状态
  if (isError || !serverInfo) {
    return (
      <Alert
        message="服务器未找到"
        description={error?.message || "无法找到指定的服务器"}
        type="error"
        showIcon
      />
    )
  }
  
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <Title level={2} className="!mb-0 !mt-0">{serverInfo.name} - 控制台</Title>
      </div>
      
      {/* 连接状态 */}
      <Alert
        message={
          isConnecting ? 
            <><Spin size="small" /> 正在连接到服务器控制台...</> :
            isConnected ? 
              '已连接到服务器控制台' : 
              '未连接到服务器控制台'
        }
        type={isConnecting ? "info" : isConnected ? "success" : "warning"}
        showIcon={!isConnecting}
        action={
          !isConnected && !isConnecting ? (
            <Button size="small" onClick={connectWebSocket}>
              重新连接
            </Button>
          ) : undefined
        }
      />
      
      {/* 服务器状态警告 */}
      {status && status !== 'HEALTHY' && (
        <Alert
          message={`服务器状态: ${status}`}
          description="只有服务器处于健康状态时才能发送命令"
          type="warning"
          showIcon
        />
      )}
      
      <Card 
        title={
          <div className="flex items-center justify-between">
            <span>服务器日志</span>
            <div className="flex items-center space-x-6">
              <div className="flex items-center space-x-2">
                <Switch 
                  checked={filterRcon} 
                  onChange={setFilterRcon} 
                  size="small"
                />
                <span className="text-sm text-gray-600">过滤 RCON 日志</span>
              </div>
              <div className="flex items-center space-x-2">
                <Switch 
                  checked={autoScroll} 
                  onChange={setAutoScroll} 
                  size="small"
                />
                <span className="text-sm text-gray-600">自动滚动</span>
              </div>
            </div>
          </div>
        } 
        className="h-full"
      >
        <div className="space-y-4">
          {/* 日志显示区域 */}
          <TextArea
            ref={logsRef}
            value={logs}
            placeholder="服务器日志将在这里显示..."
            rows={25}
            readOnly
            onScroll={handleScroll}
            className="font-mono text-sm"
            style={{
              backgroundColor: '#1e1e1e',
              color: '#ffffff',
              border: '1px solid #404040',
              resize: 'vertical'
            }}
          />
          
          {/* 命令输入 */}
          <Space.Compact style={{ width: '100%' }}>
            <Input
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder={
                status === 'HEALTHY' 
                  ? "输入服务器命令 (例如: list, say hello, weather clear)" 
                  : "服务器必须处于健康状态才能发送命令"
              }
              disabled={!isConnected || status !== 'HEALTHY'}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={sendCommand}
              disabled={!command.trim() || !isConnected || status !== 'HEALTHY'}
            >
              发送
            </Button>
          </Space.Compact>
        </div>
      </Card>
    </div>
  )
}

export default ServerConsole