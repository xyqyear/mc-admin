import { readFileSync } from 'node:fs'
import path from 'node:path'
import { defineConfig, devices } from '@playwright/test'

const output = path.resolve(process.env.BROWSER_OUTPUT_DIR ?? 'test-results/browser')
const fixturePath = process.env.MC_ADMIN_BROWSER_FIXTURE
const fixture = fixturePath ? JSON.parse(readFileSync(fixturePath, 'utf8')) : undefined

export default defineConfig({
  testDir: './browser',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  outputDir: path.join(output, 'artifacts'),
  reporter: [
    ['list'],
    ['json', { outputFile: path.join(output, 'results.json') }],
    ['html', { outputFolder: path.join(output, 'report'), open: 'never' }],
  ],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: fixture?.base_url,
    viewport: { width: 1440, height: 1000 },
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    serviceWorkers: 'block',
  },
  projects: [{ name: 'chromium' }],
})
