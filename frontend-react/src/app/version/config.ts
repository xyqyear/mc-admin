export const GITHUB_REPO = 'xyqyear/mc-admin'
export const GITHUB_ISSUE_URL_TEMPLATE = `https://github.com/${GITHUB_REPO}/issues/{id}`

export const getGithubIssueUrl = (issueId: number | string): string => {
  return GITHUB_ISSUE_URL_TEMPLATE.replace('{id}', String(issueId))
}


function parseVersion(version: string) {
  const match = /^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([\da-zA-Z-]+(?:\.[\da-zA-Z-]+)*))?(?:\+[\da-zA-Z-]+(?:\.[\da-zA-Z-]+)*)?$/.exec(version.trim())
  return {
    core: [match?.[1] ?? '0', match?.[2] ?? '0', match?.[3] ?? '0'].map(BigInt),
    prerelease: match?.[4]?.split('.') ?? [],
  }
}

export function compareVersions(a: string, b: string): number {
  const versionA = parseVersion(a)
  const versionB = parseVersion(b)

  for (let i = 0; i < 3; i++) {
    if (versionA.core[i] < versionB.core[i]) return -1
    if (versionA.core[i] > versionB.core[i]) return 1
  }

  const preA = versionA.prerelease
  const preB = versionB.prerelease
  if (!preA.length || !preB.length) {
    return preA.length === preB.length ? 0 : preA.length ? -1 : 1
  }

  for (let i = 0; i < Math.max(preA.length, preB.length); i++) {
    const left = preA[i]
    const right = preB[i]
    if (left === undefined) return -1
    if (right === undefined) return 1
    if (left === right) continue
    const leftNumeric = /^\d+$/.test(left)
    const rightNumeric = /^\d+$/.test(right)
    if (leftNumeric && rightNumeric) {
      if (BigInt(left) < BigInt(right)) return -1
      if (BigInt(left) > BigInt(right)) return 1
    } else if (leftNumeric !== rightNumeric) {
      return leftNumeric ? -1 : 1
    } else {
      return left < right ? -1 : 1
    }
  }
  return 0
}
