import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './tests/browser', timeout: 30000, expect: { timeout: 6000 }, workers: 1,
  reporter: 'list', outputDir: 'test-results',
  use: { baseURL: 'http://127.0.0.1:4179', trace: 'retain-on-failure', ...devices['Desktop Edge'], channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge' },
})
