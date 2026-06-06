import { useMemo } from 'react'

import type { SelfCheckFinding, SelfCheckRunStatus } from '@/hooks/api/selfCheckApi'
import { useSelfCheckStatus } from '@/hooks/queries/base/useSelfCheckQueries'

function isVisibleIssue(finding: SelfCheckFinding) {
  return (
    finding.status === 'failed' ||
    finding.status === 'critical' ||
    finding.severity === 'critical' ||
    finding.status === 'warning' ||
    finding.severity === 'warning'
  )
}

export function useSelfCheckHealth() {
  const statusQuery = useSelfCheckStatus()

  const health = useMemo(() => {
    const findings = statusQuery.data?.current_state?.findings ?? []
    const issues = findings.filter(isVisibleIssue)
    const criticalCount = issues.filter(
      (finding) =>
        finding.status === 'failed' ||
        finding.status === 'critical' ||
        finding.severity === 'critical'
    ).length
    const warningCount = issues.filter(
      (finding) =>
        finding.status === 'warning' || finding.severity === 'warning'
    ).length
    const status: SelfCheckRunStatus =
      criticalCount > 0 ? 'critical' : warningCount > 0 ? 'warning' : 'success'

    return {
      status,
      issues,
      issueCount: issues.length,
      criticalCount,
      warningCount,
      updatedAt: statusQuery.data?.current_state?.updated_at ?? null,
    }
  }, [statusQuery.data?.current_state])

  return {
    ...health,
    isLoading: statusQuery.isLoading,
    isError: statusQuery.isError,
    error: statusQuery.error,
  }
}
