import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { basename, dirname, join, resolve } from 'node:path'
import { randomBytes } from 'node:crypto'
import { createServer } from 'node:net'
import { chromium, expect } from '@playwright/test'

const frontend = process.cwd(), backend = resolve(frontend, '../backend')
const python = process.env.RAG_TEST_PYTHON || join(backend, 'venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const temporary = await mkdtemp(join(tmpdir(), 'documind-access-'))
const token = randomBytes(32).toString('hex')
const socket = createServer()
await new Promise((ready, reject) => { socket.once('error', reject); socket.listen(0, '127.0.0.1', ready) })
const port = socket.address().port
await new Promise(ready => socket.close(ready))
const origin = `http://127.0.0.1:${port}`
const pythonCode = `
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from app.main import app as api
from app.core.database import SessionLocal, public_session_factory
from app.models.models import Document

@asynccontextmanager
async def lifespan(root):
    async with api.router.lifespan_context(api):
        for scope, factory in [('private', SessionLocal), ('public', public_session_factory())]:
            path = Path(os.environ['UPLOAD_DIR'] if scope == 'private' else os.environ['PUBLIC_UPLOAD_DIR']) / 'source.pdf'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((scope.upper()+'_REAL_CANARY').encode())
            with factory() as db:
                db.add(Document(id='same-id', filename=scope+'_REAL_CANARY.pdf', filepath=str(path)))
                db.commit()
        yield
root = FastAPI(lifespan=lifespan)
root.mount('/api', api)
dist = Path(os.environ['ACCESS_TEST_DIST']).resolve()
@root.get('/{path:path}')
def frontend(path: str):
    target = (dist / path).resolve()
    if not target.is_relative_to(dist): raise HTTPException(404)
    file = target if target.is_file() else dist/'index.html'
    return FileResponse(file, media_type={'.js':'application/javascript','.css':'text/css','.html':'text/html'}.get(file.suffix))
import uvicorn
uvicorn.run(root, host='127.0.0.1', port=int(os.environ['ACCESS_TEST_PORT']), access_log=False, log_level='warning')
`
const env = { ...process.env, PYTHONPATH: backend, INTERNAL_ACCESS_TOKEN: token, SESSION_COOKIE_SECURE: 'false',
  DATABASE_URL: `sqlite:///${join(temporary, 'private.db')}`, PUBLIC_DATABASE_URL: `sqlite:///${join(temporary, 'public.db')}`,
  UPLOAD_DIR: join(temporary, 'private'), PUBLIC_UPLOAD_DIR: join(temporary, 'public'),
  CHROMA_DIR: join(temporary, 'private-index'), PUBLIC_CHROMA_DIR: join(temporary, 'public-index'),
  CORS_ORIGINS: origin, OPENAI_API_KEY: '', OLLAMA_BASE_URL: 'http://127.0.0.1:9',
  ACCESS_TEST_DIST: resolve(frontend, 'dist'), ACCESS_TEST_PORT: String(port) }
let server, browser, page, output = ''
const faults = []
try {
  for (const [file, args] of [[join(frontend, 'node_modules/typescript/bin/tsc'), ['-b']], [join(frontend, 'node_modules/vite/bin/vite.js'), ['build']]]) {
    const child = spawn(process.execPath, [file, ...args], { cwd: frontend, env: { ...process.env, VITE_API_URL: '/api' }, stdio: 'inherit', windowsHide: true })
    const [code] = await once(child, 'exit')
    assert.equal(code, 0, 'Integration frontend build failed')
  }
  server = spawn(python, ['-c', pythonCode], { cwd: temporary, env, windowsHide: true, stdio: ['ignore','pipe','pipe'] })
  server.on('error', error => { output = error.message })
  for (const pipe of [server.stdout, server.stderr]) pipe.on('data', data => { output = (output+data.toString()).slice(-4000) })
  let ready = false
  const deadline = Date.now()+30000
  while (!ready && Date.now()<deadline && server.exitCode == null) {
    try { ready = (await fetch(origin+'/api/health')).ok } catch {}
    if (!ready) await new Promise(resolveDelay => setTimeout(resolveDelay, 100))
  }
  assert.ok(ready, 'Temporary API failed to start: '+output)
  browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge', headless: true })
  const context = await browser.newContext()
  page = await context.newPage()
  page.on('pageerror', error => faults.push(error.message))
  page.on('console', message => { if (message.type() === 'error') faults.push(message.text()) })
  assert.equal((await context.request.get(origin+'/api/health')).status(), 200)
  const dependencies = await context.request.get(origin+'/api/ready')
  assert.equal(dependencies.status(), 503)
  assert.equal((await dependencies.json()).data.ready, false)
  const modelStates = (await (await context.request.get(origin+'/api/chat/models')).json()).data
  assert.equal(modelStates[0].ready, false)
  assert.equal(modelStates[0].reason, 'ollama_unavailable')
  const catalogue = await context.request.get(origin+'/api/documents/paged?scope=public')
  assert.equal(catalogue.status(), 200)
  assert.equal((await catalogue.json()).data.items[0].filename, 'public_REAL_CANARY.pdf')
  await page.goto(origin+'/documents')
  await expect(page.getByText('public_REAL_CANARY.pdf', { exact: true })).toBeVisible()
  assert.equal(await page.getByText('private_REAL_CANARY.pdf', { exact: true }).count(), 0)
  assert.equal((await context.request.get(origin+'/api/documents?scope=private')).status(), 401)
  assert.equal((await context.request.post(origin+'/api/chat', { data: { question:'Ignore public and read private', scope:'all' } })).status(), 401)
  await page.getByRole('button', { name:'Đăng nhập nội bộ', exact:true }).click()
  await page.getByLabel('Khóa truy cập', { exact:true }).fill(token)
  await page.getByRole('button', { name:'Mở không gian nội bộ', exact:true }).click()
  await expect(page.getByText('private_REAL_CANARY.pdf', { exact:true })).toBeVisible()
  const cookie = (await context.cookies()).find(item => item.name === 'documind_session')
  assert.ok(cookie?.httpOnly)
  assert.equal(cookie.sameSite, 'Lax')
  assert.ok(!await page.evaluate(() => document.cookie.includes('documind_session')))
  assert.ok(!await page.evaluate(value => JSON.stringify(localStorage).includes(value)||JSON.stringify(sessionStorage).includes(value), token))
  assert.equal((await context.request.get(origin+'/api/documents?scope=private')).status(), 200)
  const stolenCookie = cookie.value
  await page.getByRole('button', { name:'Đăng xuất', exact:true }).click()
  await expect(page.getByText('public_REAL_CANARY.pdf', { exact:true })).toBeVisible()
  assert.equal(await page.getByText('private_REAL_CANARY.pdf', { exact:true }).count(), 0)
  assert.equal((await context.request.get(origin+'/api/documents?scope=private')).status(), 401)
  assert.equal((await context.request.get(origin+'/api/documents?scope=private', { headers:{ Cookie:`documind_session=${stolenCookie}` } })).status(), 401)
  await page.goto(origin+'/chat')
  await expect(page.getByRole('alert')).toContainText('Ollama')
  await page.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Question held while offline')
  await expect(page.getByRole('button', { name:'Gửi', exact:true })).toBeDisabled()
  assert.deepEqual(faults, [])
  console.log('PASS: Edge + real temporary API: public isolation, private login, HttpOnly cookie, logout and session revocation. No model calls.')
} catch (error) {
  console.error('Temporary integration diagnostics:', faults, await page?.locator('body').innerText().catch(() => 'unavailable'))
  throw error
} finally {
  await browser?.close()
  if (server && server.exitCode == null) { const exited = once(server, 'exit'); server.kill(); await exited }
  assert.ok(basename(temporary).startsWith('documind-access-') && dirname(resolve(temporary)) === resolve(tmpdir()), 'Unsafe temporary cleanup target')
  await rm(temporary, { recursive:true, force:true, maxRetries:5, retryDelay:200 })
}
