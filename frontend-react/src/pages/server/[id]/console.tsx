import React, { useState, useRef, useEffect, useCallback } from 'react'
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
import { useServerConsoleWebSocket } from '@/hooks/useServerConsoleWebSocket'
import { log } from '@/utils/devLogger'

const { Title } = Typography
const { TextArea } = Input

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
  const [filterRcon, setFilterRcon] = useState(true) // 默认开启RCON过滤
  const [autoScroll, setAutoScroll] = useState(true) // 自动滚动开关
  
  // Refs
  const logsRef = useRef<any>(null) // 使用any类型避免TypeScript错误
  
  // WebSocket回调函数
  const handleLogsUpdate = useCallback((content: string) => {
    setLogs(prev => prev + content)
  }, [])
  
  const handleLogsRefresh = useCallback((content: string) => {
    setLogs(content)
    setAutoScroll(true)
  }, [])
  
  const handleCommandResult = useCallback((command: string, result: string) => {
    const commandLog = `> ${command}\n${result}\n`
    setLogs(prev => prev + commandLog)
    setAutoScroll(true)
  }, [])
  
  const handleError = useCallback((message: string) => {
    setLogs(prev => prev + `[ERROR] ${message}\n`)
  }, [])
  
  const handleInfo = useCallback((message: string) => {
    setLogs(prev => prev + `[INFO] ${message}\n`)
  }, [])
  
  const handleAutoScrollEnable = useCallback(() => {
    setAutoScroll(true)
  }, [])
  
  // 使用WebSocket hook
  const {
    isConnected,
    isConnecting,
    connect: connectWebSocket,
    sendCommand: wsCommandSend
  } = useServerConsoleWebSocket({
    serverId: id || '',
    token: token || '',
    filterRcon,
    onLogsUpdate: handleLogsUpdate,
    onLogsRefresh: handleLogsRefresh,
    onCommandResult: handleCommandResult,
    onError: handleError,
    onInfo: handleInfo,
    onAutoScrollEnable: handleAutoScrollEnable
  })
  
  // 发送命令
  const sendCommand = () => {
    if (!command.trim() || !isConnected) return
    
    if (wsCommandSend(command)) {
      setCommand('')
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
    // 只有在有必要信息且未连接时才尝试连接
    if (id && token && hasServerInfo && !isConnecting && !isConnected) {
      connectWebSocket()
    }
  }, [id, hasServerInfo, token, connectWebSocket, isConnecting, isConnected])

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