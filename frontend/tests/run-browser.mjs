import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { resolve } from 'node:path'

const env = { ...process.env, VITE_API_URL: 'http://127.0.0.1:59998' }
const run = (file, args) => new Promise((resolveCode, reject) => {
  const child = spawn(process.execPath, [file, ...args], { cwd: process.cwd(), env, stdio: 'inherit', windowsHide: true })
  child.once('error', reject)
  child.once('exit', code => resolveCode(code ?? 1))
})
let server
try {
  let code = await run(resolve('node_modules/typescript/bin/tsc'), ['-b'])
  if (code !== 0) throw new Error('TypeScript build failed')
  code = await run(resolve('node_modules/vite/bin/vite.js'), ['build'])
  if (code !== 0) throw new Error('Frontend build failed')
  let listening = false
  server = spawn(process.execPath, [resolve('node_modules/vite/bin/vite.js'), 'preview', '--host', '127.0.0.1', '--port', '4179', '--strictPort', '--mode', 'browser-test'],
    { cwd: process.cwd(), env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true })
  server.stdout.on('data', chunk => { process.stdout.write(chunk); if (chunk.toString().includes('http://127.0.0.1:4179')) listening = true })
  server.stderr.on('data', chunk => process.stderr.write(chunk))
  let startError
  server.once('error', error => { startError = error })
  const deadline = Date.now() + 30000
  while (!listening) {
    if (startError || server.exitCode != null || Date.now() > deadline) throw startError || new Error('Test server did not start; check port 4179')
    await new Promise(resolveDelay => setTimeout(resolveDelay, 100))
  }
  process.exitCode = await run(resolve('node_modules/@playwright/test/cli.js'), ['test', ...process.argv.slice(2)])
} catch (error) {
  process.stderr.write(`${error.message}\n`)
  process.exitCode = 1
} finally {
  // This is the exact child PID started above, never an unrelated dev server.
  if (server && server.exitCode == null) {
    const exited = once(server, 'exit')
    server.kill()
    await exited
  }
}
