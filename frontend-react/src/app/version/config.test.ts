import { describe, expect, it } from 'vitest'
import { compareVersions } from './config'

describe('version precedence', () => {
  it.each([
    ['5.3.0', '6.0.0-beta.1'],
    ['6.0.0-beta.1', '6.0.0-beta.2'],
    ['6.0.0-beta.2', '6.0.0-beta.10'],
    ['6.0.0-beta.10', '6.0.0'],
    ['6.0.0', '6.0.1-alpha'],
    ['6.0.0-1', '6.0.0-alpha'],
    ['6.0.0-alpha', '6.0.0-alpha.1'],
    ['6.0.0-alpha.1', '6.0.0-alpha.beta'],
    ['6.0.0-beta', '6.0.0-beta.2'],
    ['6.0.0-beta.11', '6.0.0-rc.1'],
    ['6.0.0-beta.9007199254740992', '6.0.0-beta.9007199254740993'],
  ])('orders %s before %s', (older, newer) => {
    expect(compareVersions(older, newer)).toBe(-1)
    expect(compareVersions(newer, older)).toBe(1)
  })

  it.each([
    ['6.0.0-beta.1', '6.0.0-beta.1'],
    ['6.0.0-beta.1+build.10', '6.0.0-beta.1+build.20'],
    ['6.0.0+build.1', '6.0.0'],
    ['6.0', '6.0.0'],
    ['v6.0.0-beta.1', '6.0.0-beta.1'],
    ['', '0.0.0'],
    ['invalid stored version', '0.0.0'],
  ])('gives %s and %s equal precedence', (left, right) => {
    expect(compareVersions(left, right)).toBe(0)
  })
})
