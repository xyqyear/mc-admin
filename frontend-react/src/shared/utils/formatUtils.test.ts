import { describe, expect, it } from 'vitest';
import { formatBytes, formatDuration, formatFileSize } from './formatUtils';

describe('file size display', () => {
  it.each([
    { bytes: 0, expected: '-' },
    { bytes: 1023, expected: '1023 B' },
    { bytes: 1024, expected: '1 KB' },
    { bytes: 1234, expected: '1.21 KB' },
    { bytes: 1048576, expected: '1 MB' },
    { bytes: 1073741824, expected: '1 GB' },
  ])('retains table defaults for $bytes bytes', ({ bytes, expected }) => {
    expect(formatFileSize(bytes)).toBe(expected);
  });

  it.each([
    { bytes: 0, expected: '0 B' },
    { bytes: 1234, expected: '1.2 KB' },
    { bytes: 1536, expected: '1.5 KB' },
    { bytes: 1048576, expected: '1 MB' },
  ])('retains upload labels for $bytes bytes', ({ bytes, expected }) => {
    expect(formatFileSize(bytes, { decimals: 1, zeroValue: '0 B' })).toBe(expected);
  });

  it('retains terabyte units in search results', () => {
    expect(formatFileSize(1099511627776, {
      decimals: 1,
      zeroValue: '0 B',
      terabytes: true,
    })).toBe('1 TB');
  });

  it.each([
    { bytes: 0, decimals: undefined, expected: '0 B' },
    { bytes: 1234, decimals: undefined, expected: '1.2 KB' },
    { bytes: 1234, decimals: 2, expected: '1.21 KB' },
    { bytes: 1234, decimals: -1, expected: '1 KB' },
    { bytes: 1099511627776, decimals: undefined, expected: '1 TB' },
  ])('retains archive progress labels for $bytes bytes at $decimals decimals', ({ bytes, decimals, expected }) => {
    expect(formatBytes(bytes, decimals)).toBe(expected);
  });
});

describe('player duration display', () => {
  it.each([
    { seconds: 0, expected: '0分钟' },
    { seconds: 59, expected: '0分钟' },
    { seconds: 60, expected: '1分钟' },
    { seconds: 3599, expected: '59分钟' },
    { seconds: 3600, expected: '1小时 0分钟' },
    { seconds: 3660, expected: '1小时 1分钟' },
    { seconds: 86399, expected: '23小时 59分钟' },
    { seconds: 86400, expected: '1天 0小时' },
    { seconds: 90000, expected: '1天 1小时' },
    { seconds: 172800, expected: '2天 0小时' },
  ])('retains accumulated playtime for $seconds seconds', ({ seconds, expected }) => {
    expect(formatDuration(seconds)).toBe(expected);
  });

  it.each([
    { seconds: 0, expected: '0分钟' },
    { seconds: 86400, expected: '24小时 0分钟' },
    { seconds: 90000, expected: '25小时 0分钟' },
  ])('retains online-session hours for $seconds seconds', ({ seconds, expected }) => {
    expect(formatDuration(seconds, false)).toBe(expected);
  });
});
