import React, { useState, useRef, useEffect, useCallback } from 'react'
import {
  Card,
  Input,
  Button,
  Alert,
  Space,
  Spin,
  Switch
} from 'antd'
import {
  SendOutlined,
  CodeOutlined
} from '@ant-design/icons'
import { useParams } from 'react-router-dom'
import { useServerDetailQueries } from '@/hooks/queries/page/useServerDetailQueries'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import PageHeader from '@/components/layout/PageHeader'
import { useToken } from '@/stores/useTokenStore'
import { useServerConsoleWebSocket } from '@/hooks/useServerConsoleWebSocket'
import { log } from '@/utils/devLogger'

const { TextArea } = Input

const ServerConsole: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const token = useToken()

  // 使用数据管理系统
  const { useServerConsoleData } = useServerDetailQueries(id || '')

  const {
    serverInfo,
    status,
    isLoading,
    isError,
    error,
    hasServerInfo,
    refetch,
  } = useServerConsoleData()

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


  const handleError = useCallback((message: string) => {
    setLogs(prev => prev + `[ERROR] ${message}\n`)
  }, [])

  const handleInfo = useCallback((message: string) => {
    setLogs(prev => prev + `[INFO] ${message}\n`)
  }, [])

  const handleAutoScrollEnable = useCallback(() => {
    setAutoScroll(true)
  }, [])

  const handleErrorDisconnect = useCallback(() => {
    // 收到错误消息时刷新服务器状态
    // useEffect 会自动处理重连逻辑
    refetch()
  }, [refetch])

  // 使用WebSocket hook
  const {
    isConnected,
    isConnecting,
    connect: connectWebSocket,
    sendCommand: wsCommandSend
  } = useServerConsoleWebSocket({
    serverId: id || '',
    token: token || '',
    serverStatus: status || null,
    filterRcon,
    onLogsUpdate: handleLogsUpdate,
    onLogsRefresh: handleLogsRefresh,
    onError: handleError,
    onInfo: handleInfo,
    onAutoScrollEnable: handleAutoScrollEnable,
    onErrorDisconnect: handleErrorDisconnect
  })

  // 检查是否可以发送命令
  const canSendCommand = useCallback(() => {
    if (!isConnected) return false
    if (!status) return false
    return ['RUNNING', 'STARTING', 'HEALTHY'].includes(status)
  }, [isConnected, status])

  // 发送命令
  const sendCommand = () => {
    if (!command.trim() || !canSendCommand()) return

    wsCommandSend(command)
    setCommand('')
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

  // 当服务器ID变化时清空日志
  useEffect(() => {
    setLogs('')
  }, [id])

  // 检查服务器状态是否允许WebSocket连接
  const canConnectWebSocket = useCallback(() => {
    if (!status) return false
    return status !== 'REMOVED' && status !== 'EXISTS'
  }, [status])

  // 组件挂载时连接WebSocket
  useEffect(() => {
    // 只有在有必要信息且未连接时，并且服务器状态允许连接时才尝试连接
    if (id && token && hasServerInfo && !isConnecting && !isConnected && canConnectWebSocket()) {
      connectWebSocket()
    }
  }, [id, hasServerInfo, token, connectWebSocket, isConnecting, isConnected, canConnectWebSocket])

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
      <PageHeader
        title="控制台"
        icon={<CodeOutlined />}
        serverTag={serverInfo.name}
      />

      {/* 连接状态 */}
      <Alert
        message={
          isConnecting ?
            <><Spin size="small" /> 正在连接到服务器控制台...</> :
            isConnected ?
              '已连接到服务器控制台' :
              !canConnectWebSocket() ?
                '服务器必须处于已停止、运行、启动或健康状态才能连接控制台' :
                '未连接到服务器控制台'
        }
        type={
          isConnecting ? "info" :
            isConnected ? "success" :
              !canConnectWebSocket() ? "warning" :
                "warning"
        }
        showIcon={!isConnecting}
        action={
          !isConnected && !isConnecting && canConnectWebSocket() ? (
            <Button size="small" onClick={connectWebSocket}>
              重新连接
            </Button>
          ) : undefined
        }
      />


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
                canSendCommand()
                  ? "输入服务器命令 (例如: list, say hello, weather clear)"
                  : "服务器控制台已连接并且服务器正在运行才能发送命令"
              }
              disabled={!canSendCommand()}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={sendCommand}
              disabled={!command.trim() || !canSendCommand()}
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