import { expect, it } from 'vitest'
import { normalizeUuid } from './identity'

it.each([
  [null, null],
  [undefined, null],
  ['', null],
  ['123E4567-E89B-42D3-A456-426614174000', '123e4567e89b42d3a456426614174000'],
  ['123e4567e89b42d3a456426614174000', '123e4567e89b42d3a456426614174000'],
  ['123e4567e89b42d3a45642661417400', null],
  ['123e4567e89b42d3a4564266141740000', null],
  ['123e4567e89b42d3a45642661417400g', null],
] as const)('uses one UUID identity for %s', (input, expected) => {
  expect(normalizeUuid(input)).toBe(expected)
})
