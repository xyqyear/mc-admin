import { useState, useEffect } from 'react'
import { currentVersion } from '@/config/versionConfig'
import { compareVersions } from '@/config/versionConfig'

const VERSION_STORAGE_KEY = 'mc-admin-last-seen-version'
const REMIND_TIME_STORAGE_KEY = 'mc-admin-remind-time'

interface VersionCheckResult {
  shouldShowModal: boolean
  fromVersion: string
  toVersion: string
  showModal: () => void
  handleClose: () => void
  handleRemindLater: () => void
}

export function useVersionCheck(): VersionCheckResult {
  const [shouldShowModal, setShouldShowModal] = useState(false)
  const [fromVersion, setFromVersion] = useState('')

  useEffect(() => {
    const checkVersion = () => {
      const lastSeenVersion = localStorage.getItem(VERSION_STORAGE_KEY)
      const remindTimeStr = localStorage.getItem(REMIND_TIME_STORAGE_KEY)

      // 如果这是首次访问，设置当前版本但不显示弹窗
      if (!lastSeenVersion) {
        localStorage.setItem(VERSION_STORAGE_KEY, currentVersion)
        return
      }

      // 检查是否有新版本
      if (compareVersions(currentVersion, lastSeenVersion) > 0) {
        // 如果设置了稍后提醒，检查时间是否已过
        if (remindTimeStr) {
          const remindTime = new Date(remindTimeStr).getTime()
          const now = new Date().getTime()
          const oneHour = 60 * 60 * 1000 // 1小时的毫秒数

          // 如果还没到提醒时间，不显示弹窗
          if (now < remindTime + oneHour) {
            return
          }
        }

        // 显示版本更新弹窗
        setFromVersion(lastSeenVersion)
        setShouldShowModal(true)
      }
    }

    // 延迟执行检查，确保页面加载完成
    const timer = setTimeout(checkVersion, 1000)

    return () => clearTimeout(timer)
  }, [])

  const showModal = () => {
    setShouldShowModal(true)
  }

  const handleClose = () => {
    // 用户点击"明白了"，保存最新版本并清除提醒时间
    localStorage.setItem(VERSION_STORAGE_KEY, currentVersion)
    localStorage.removeItem(REMIND_TIME_STORAGE_KEY)
    setShouldShowModal(false)
  }

  const handleRemindLater = () => {
    // 用户点击"稍后提醒我"，保存当前时间
    localStorage.setItem(REMIND_TIME_STORAGE_KEY, new Date().toISOString())
    setShouldShowModal(false)
  }

  return {
    shouldShowModal,
    fromVersion,
    toVersion: currentVersion,
    showModal,
    handleClose,
    handleRemindLater
  }
}