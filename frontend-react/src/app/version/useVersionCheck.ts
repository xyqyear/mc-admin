import { useState, useEffect } from 'react'
import { compareVersions } from '@/app/version/config'
import { useReleaseData } from './releaseData'

const VERSION_STORAGE_KEY = 'mc-admin-last-seen-version'
const REMIND_TIME_STORAGE_KEY = 'mc-admin-remind-time'

interface VersionCheckResult {
  shouldShowDialog: boolean
  fromVersion: string
  toVersion: string
  showDialog: () => void
  handleClose: () => void
  handleRemindLater: () => void
}

export function useVersionCheck(): VersionCheckResult {
  const currentVersion = useReleaseData().data?.currentVersion ?? ''
  const [shouldShowDialog, setShouldShowDialog] = useState(false)
  const [fromVersion, setFromVersion] = useState('')

  useEffect(() => {
    if (!currentVersion) return
    const checkVersion = () => {
      const lastSeenVersion = localStorage.getItem(VERSION_STORAGE_KEY)
      const remindTimeStr = localStorage.getItem(REMIND_TIME_STORAGE_KEY)

      // First visit: record the current version silently — no upgrade dialog.
      if (!lastSeenVersion) {
        localStorage.setItem(VERSION_STORAGE_KEY, currentVersion)
        return
      }

      if (compareVersions(currentVersion, lastSeenVersion) > 0) {
        // "Remind later" suppresses the dialog for one hour.
        if (remindTimeStr) {
          const remindTime = new Date(remindTimeStr).getTime()
          const now = new Date().getTime()
          const oneHour = 60 * 60 * 1000

          if (now < remindTime + oneHour) {
            return
          }
        }

        setFromVersion(lastSeenVersion)
        setShouldShowDialog(true)
      }
    }

    // Defer past initial render so the dialog doesn't fight layout.
    const timer = setTimeout(checkVersion, 1000)

    return () => clearTimeout(timer)
  }, [currentVersion])

  const showDialog = () => {
    setShouldShowDialog(true)
  }

  const handleClose = () => {
    if (!currentVersion) return
    localStorage.setItem(VERSION_STORAGE_KEY, currentVersion)
    localStorage.removeItem(REMIND_TIME_STORAGE_KEY)
    setShouldShowDialog(false)
  }

  const handleRemindLater = () => {
    if (!currentVersion) {
      setShouldShowDialog(false)
      return
    }
    localStorage.setItem(REMIND_TIME_STORAGE_KEY, new Date().toISOString())
    setShouldShowDialog(false)
  }

  return {
    shouldShowDialog,
    fromVersion,
    toVersion: currentVersion,
    showDialog,
    handleClose,
    handleRemindLater
  }
}
