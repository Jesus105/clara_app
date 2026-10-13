import {defineConfig} from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {baseURL: 'http://127.0.0.1:8100', viewport: {width: 1440, height: 1000}, trace: 'retain-on-failure'},
  webServer: {command: '../.venv/bin/python ../scripts/e2e_server.py', url: 'http://127.0.0.1:8100/api/health', timeout: 60000, reuseExistingServer: false},
})

