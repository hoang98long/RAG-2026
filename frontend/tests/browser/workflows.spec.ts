import { test as base, expect, type Route, type BrowserContext } from '@playwright/test'
const API = 'http://127.0.0.1:59998'
const ORIGIN = 'http://127.0.0.1:4179'
const fixtureDocument = (scope = 'private') => ({ id: `${scope}-doc`, filename: `${scope}.pdf`, scope, upload_time: '2026-10-14T10:00:00Z' })
const sources = [{ document: 'public.pdf', document_id: 'public-doc', scope: 'public', source_id: 'S1', page: 7, chunk_index: 53, index_version: 'documents_v5_fixture', digest: '0123456789abcdef', content: 'Bảo hành 24 tháng.' }]
const coverage = { completeness_unverified: false, truncated: false, exhaustive_requested: false, evidence_chunks: 1, query_count: 1 }
const wait = (milliseconds: number) => new Promise(resolve => setTimeout(resolve, milliseconds))
async function ok(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': ORIGIN, 'Access-Control-Allow-Credentials': 'true' }, body: JSON.stringify({ success: true, data }) })
}
async function fail(route: Route, status: number, detail: string) {
  await route.fulfill({ status, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': ORIGIN, 'Access-Control-Allow-Credentials': 'true' }, body: JSON.stringify({ detail }) })
}
async function intercept(context: BrowserContext, pattern: string, handler: (route: Route) => Promise<unknown>) {
  await context.route(pattern, route => route.request().method() === 'OPTIONS' ? route.fallback() : handler(route))
}
const test = base.extend<{ faults: string[] }>({
  faults: async ({ page, context }, use) => {
    const faults: string[] = []
    page.on('pageerror', error => faults.push(error.message))
    await context.route(`${API}/**`, async route => {
      const request = route.request(), url = new URL(request.url()), scope = url.searchParams.get('scope') || 'private'
      if (request.method() === 'OPTIONS') { await route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': ORIGIN, 'Access-Control-Allow-Credentials': 'true', 'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type,Authorization,Idempotency-Key' } }); return }
      if (url.pathname === '/auth/session') return ok(route, { private_access: true, private_configured: true })
      if (url.pathname === '/chat/models') return ok(route, [
        { id: 'qwen2.5:7b', label: 'Qwen 2.5 · 7B', configured: true },
        { id: 'llama3.1:70b', label: 'Llama 3.1 · 70B', configured: true },
        { id: 'openai', label: 'OpenAI', configured: true },
      ])
      if (url.pathname === '/documents/paged') return ok(route, { items: [fixtureDocument(scope)], total: 1, offset: 0, limit: 50 })
      if (url.pathname === '/dashboard') return ok(route, { documents: 1, chats: 2, reports: 0 })
      if (url.pathname === '/documents/upload-limits') return ok(route, { max_file_mb: 200, max_request_mb: 512, max_files: 20 })
      if (url.pathname.endsWith('/content')) {
        const target = Number(url.searchParams.get('chunk') || 0)
        const offset = url.searchParams.has('chunk') ? Math.floor(target / 50) * 50 : Number(url.searchParams.get('offset') || 0)
        return ok(route, { ...fixtureDocument(scope), file_type: 'pdf', offset, limit: 50, total: 150, target_found: true,
          chunks: Array.from({ length: 50 }, (_, index) => ({ chunk_index: offset+index, page: 7, content: `Nội dung ${offset+index}` })) })
      }
      return fail(route, 404, 'Endpoint giả lập chưa được cấu hình')
    })
    await use(faults)
    expect(faults).toEqual([])
  },
})

test('chat submits once, keeps default model, hides codes and opens exact public source', async ({ page, context, faults }) => {
  const requests: unknown[] = []
  await intercept(context, `${API}/chat`, async route => { requests.push(route.request().postDataJSON()); await wait(200); await ok(route, { answer: 'Bảo hành 24 tháng [S1, S2].', sources, coverage }) })
  await page.goto('/chat')
  await page.getByLabel('Ngu\u1ed3n t\u00e0i li\u1ec7u').selectOption('public')
  await expect(page.getByLabel('Mô hình trả lời')).toHaveValue('qwen2.5:7b')
  await page.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Thời hạn?')
  await page.locator('form').evaluate(form => { form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })) })
  await expect(page.locator('article')).toContainText('Bảo hành 24 tháng.')
  await expect(page.locator('article')).not.toContainText('[S1')
  expect(requests).toEqual([{ question: 'Thời hạn?', model: 'qwen2.5:7b', scope: 'public' }])
  const link = page.getByRole('link', { name: /public.pdf.*Trang 7.*Đoạn 54/ }).first()
  await expect(link).toHaveAttribute('href', /scope=public.*version=documents_v5_fixture.*digest=0123456789abcdef/)
  const popupWait = page.waitForEvent('popup')
  await link.click()
  const popup = await popupWait
  await expect(popup.locator('article').filter({ hasText: 'Nguồn được trích dẫn' })).toContainText('Nội dung 53')
  await popup.close()
})

test('switching to OpenAI clears draft and restricts requests to public', async ({ page, context, faults }) => {
  let request: any
  await intercept(context, `${API}/chat`, async route => { request = route.request().postDataJSON(); await ok(route, { answer: 'Thông tin public [S1]', sources, coverage }) })
  await page.goto('/chat')
  await page.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Nội dung nội bộ chưa gửi')
  await page.getByLabel('Mô hình trả lời').selectOption('openai')
  await expect(page.getByPlaceholder('Đặt câu hỏi về tài liệu...')).toHaveValue('')
  await expect(page.getByLabel('Nguồn tài liệu')).toHaveValue('public')
  await expect(page.getByLabel('Nguồn tài liệu')).toBeDisabled()
  await page.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Thông tin public?')
  await page.getByRole('button', { name: 'Gửi', exact: true }).click()
  await expect(page.locator('article')).toContainText('Thông tin public')
  expect(request.scope).toBe('public')
  expect(request.model).toBe('openai')
})

test('delete failure is shown without unhandled errors or automatic retries', async ({ page, context, faults }) => {
  let calls = 0
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await intercept(context, `${API}/documents/private-doc*`, async route => { calls++; await pending; await fail(route, 403, 'Không thể xóa tài liệu trong kho này') })
  await page.goto('/documents')
  await page.getByTitle('Xóa', { exact: true }).click()
  await page.getByRole('button', { name: 'Xóa tài liệu', exact: true }).click()
  try { await expect(page.getByLabel('Kho tài liệu')).toBeDisabled() } finally { release() }
  await expect(page.getByRole('alert')).toContainText('Không thể xóa tài liệu trong kho này')
  await expect(page.getByLabel('Kho tài liệu')).toBeEnabled()
  expect(calls).toBe(1)
})


test('outdated source reports 409 once and never shows an old document', async ({ page, context, faults }) => {
  let calls = 0
  await intercept(context, `${API}/documents/public-doc/content*`, async route => { calls++; await fail(route, 409, 'Nguồn thuộc chỉ mục cũ. Hãy hỏi lại.') })
  await page.goto('/documents/public-doc?scope=public&chunk=53&version=old&digest=0123456789abcdef')
  await expect(page.getByRole('alert')).toContainText('Nguồn thuộc chỉ mục cũ')
  await wait(1400)
  expect(calls).toBe(1)
  await expect(page.locator('article')).toHaveCount(0)
})

test('returning to source page revalidates its fingerprint', async ({ page, context, faults }) => {
  const requests: URL[] = []
  await intercept(context, `${API}/documents/public-doc/content*`, async route => {
    const url = new URL(route.request().url()); requests.push(url)
    if (requests.length === 3) return fail(route, 409, 'Nội dung đoạn nguồn đã thay đổi')
    await route.fallback()
  })
  await page.goto('/documents/public-doc?scope=public&chunk=53&version=documents_v5_fixture&digest=0123456789abcdef')
  await expect(page.locator('article').filter({ hasText: 'Nguồn được trích dẫn' })).toContainText('Nội dung 53')
  await page.getByRole('button', { name: 'Phần tiếp', exact: true }).click()
  await expect(page.getByText('Đoạn 101–150', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Phần trước', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Nội dung đoạn nguồn đã thay đổi')
  expect(requests[2].searchParams.get('digest')).toBe('0123456789abcdef')
  await expect(page.locator('article')).toHaveCount(0)
})

test('upload continues across navigation and prevents duplicate clicks', async ({ page, context, faults }) => {
  let calls = 0
  await intercept(context, `${API}/documents/upload?*`, async route => { calls++; await wait(1200); await ok(route, [fixtureDocument('public')]) })
  await page.goto('/upload')
  await page.getByLabel('Kho tài liệu').selectOption('public')
  await page.locator('input[type=file]').setInputFiles({ name: 'safe.pdf', mimeType: 'application/pdf', buffer: Buffer.from('PDF fixture') })
  await page.getByRole('button', { name: 'Tải lên và xử lý', exact: true }).click()
  await page.getByRole('link', { name: 'Hỏi đáp', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Đang tải và xử lý tài liệu' })).toBeVisible()
  await page.getByRole('link', { name: 'Tải tài liệu', exact: true }).click()
  await expect(page.getByLabel('Kho tài liệu')).toHaveValue('public')
  await expect(page.getByRole('status').filter({ hasText: 'thành công 1 tài liệu' })).toBeVisible()
  expect(calls).toBe(1)
})

test('retrying failed upload keeps its identifier and works without randomUUID', async ({ page, context, faults }) => {
  await page.addInitScript(() => { Object.defineProperty(crypto, 'randomUUID', { value: undefined, configurable: true }) })
  const identifiers: string[] = []
  await intercept(context, `${API}/documents/upload?*`, async route => {
    identifiers.push(route.request().headers()['idempotency-key'])
    if (identifiers.length === 1) return fail(route, 502, 'Kết nối bị gián đoạn')
    await ok(route, [fixtureDocument()])
  })
  await page.goto('/upload')
  await page.locator('input[type=file]').setInputFiles({ name: 'same.pdf', mimeType: 'application/pdf', buffer: Buffer.from('PDF fixture') })
  await page.getByRole('button', { name: 'Tải lên và xử lý', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Kết nối bị gián đoạn')
  await page.getByRole('button', { name: 'Tải lên và xử lý', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: 'thành công' })).toBeVisible()
  expect(identifiers[0]).toMatch(/^[a-f0-9-]{36}$/)
  expect(identifiers[0]).toBe(identifiers[1])
})

test('switching upload scope drops private queued files and rejects unsupported files', async ({ page, faults }) => {
  await page.goto('/upload')
  await page.locator('input[type=file]').setInputFiles({ name: 'bad.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('fixture') })
  await expect(page.getByRole('alert')).toContainText('chỉ hỗ trợ PDF hoặc DOCX')
  await page.locator('input[type=file]').setInputFiles({ name: 'private.pdf', mimeType: 'application/pdf', buffer: Buffer.from('fixture') })
  await expect(page.getByText('Tệp chờ tải (1)', { exact: true })).toBeVisible()
  await page.getByLabel('Kho tài liệu').selectOption('public')
  await expect(page.getByText('Tệp chờ tải (1)', { exact: true })).toHaveCount(0)
})

test('invalid source URL does not request a private document', async ({ page, context, faults }) => {
  let reads = 0
  await intercept(context, `${API}/documents/shared/content*`, async route => { reads++; await route.fallback() })
  await page.goto('/documents/shared?scope=typo&chunk=99999999999999999999')
  await expect(page.getByRole('alert')).toContainText('Liên kết tài liệu không hợp lệ')
  expect(reads).toBe(0)
})

test('clipboard rejection is handled in report preview', async ({ page, context, faults }) => {
  await page.addInitScript(() => { Object.defineProperty(navigator, 'clipboard', { value: { writeText: () => Promise.reject(new Error('Denied')) }, configurable: true }) })
  await intercept(context, `${API}/report`, route => ok(route, { content: 'Báo cáo có bằng chứng [S1].', sources: [{ ...sources[0], scope: 'private' }] }))
  await page.goto('/report')
  await page.getByLabel('Tiêu đề').fill('Báo cáo')
  await page.getByRole('button', { name: 'Tạo báo cáo', exact: true }).click()
  await expect(page.locator('article')).toContainText('Báo cáo có bằng chứng.')
  await page.getByRole('button', { name: 'Sao chép báo cáo', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Không thể sao chép')
})

test('mobile chat scrolls internally without horizontal overflow', async ({ page, context, faults }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await intercept(context, `${API}/chat`, route => ok(route, { answer: Array.from({ length: 70 }, (_, i) => `- Mục ${i+1}: nội dung được dẫn [S1]`).join('\n'), sources: [{ ...sources[0], document: 'A'.repeat(200)+'.pdf' }], coverage }))
  await page.goto('/chat')
  await page.getByLabel('Ngu\u1ed3n t\u00e0i li\u1ec7u').selectOption('public')
  await page.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Danh sách?')
  await page.getByRole('button', { name: 'Gửi', exact: true }).click()
  await expect(page.locator('article')).toContainText('Mục 70')
  expect(await page.getByTestId('chat-scroll').evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/chat-mobile.png', fullPage: true })
})

test('answer does not automatically load external image URLs', async ({ page, context, faults }) => {
  let remoteReads = 0
  await context.route('https://untrusted.example/**', async route => { remoteReads++; await route.abort() })
  await intercept(context, `${API}/chat`, route => ok(route, { answer: '![Hình minh họa](https://untrusted.example/tracker?text=private)\n\nBảo hành 24 tháng [S1]', sources, coverage }))
  await page.goto('/chat')
  await page.getByLabel('Ngu\u1ed3n t\u00e0i li\u1ec7u').selectOption('public')
  await page.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Thông tin?')
  await page.getByRole('button', { name: 'Gửi', exact: true }).click()
  await expect(page.locator('article')).toContainText('Bảo hành 24 tháng')
  await expect(page.locator('article img')).toHaveCount(0)
  expect(remoteReads).toBe(0)
})

test('chat failure restores the question and preserves a newer draft on retry failure', async ({ page, context, faults }) => {
  let calls = 0
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await intercept(context, `${API}/chat`, async route => {
    calls++
    if (calls === 2) await pending
    await fail(route, 503, `Dịch vụ chưa sẵn sàng ${calls}`)
  })
  await page.goto('/chat')
  const input = page.getByPlaceholder('Đặt câu hỏi về tài liệu...')
  await input.fill('Câu hỏi cần thử lại')
  await page.getByRole('button', { name: 'Gửi', exact: true }).click()
  await expect(page.locator('article').first()).toContainText('Dịch vụ chưa sẵn sàng 1')
  await expect(input).toHaveValue('Câu hỏi cần thử lại')
  await page.getByRole('button', { name: 'Gửi', exact: true }).click()
  try { await input.fill('Câu hỏi mới đang soạn') } finally { release() }
  await expect(page.locator('article').last()).toContainText('Dịch vụ chưa sẵn sàng 2')
  await expect(input).toHaveValue('Câu hỏi mới đang soạn')
  expect(calls).toBe(2)
})

test('background upload banner leaves the desktop chat input inside the viewport', async ({ page, context, faults }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await intercept(context, `${API}/documents/upload?*`, async route => { await pending; await ok(route, [fixtureDocument()]) })
  await page.goto('/upload')
  await page.locator('input[type=file]').setInputFiles({ name: 'background.pdf', mimeType: 'application/pdf', buffer: Buffer.from('fixture') })
  await page.getByRole('button', { name: 'Tải lên và xử lý', exact: true }).click()
  try {
    await page.getByRole('link', { name: 'Hỏi đáp', exact: true }).click()
    await expect(page.getByRole('status').filter({ hasText: 'Đang tải và xử lý tài liệu' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Gửi', exact: true })).toBeVisible()
    const bounds = await page.getByRole('button', { name: 'Gửi', exact: true }).boundingBox()
    expect(bounds).not.toBeNull()
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(900)
  } finally { release() }
  await expect(page.getByRole('status').filter({ hasText: 'Đang tải và xử lý tài liệu' })).toHaveCount(0)
  const bounds = await page.getByRole('button', { name: 'Gửi', exact: true }).boundingBox()
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(900)
})

test('anonymous users only see public and cannot navigate to management actions', async ({ page, context, faults }) => {
  const reads: string[] = []
  await intercept(context, `${API}/auth/session`, route => ok(route, { private_access: false, private_configured: true }))
  await intercept(context, `${API}/documents/paged*`, async route => { reads.push(route.request().url()); await route.fallback() })
  await page.goto('/chat')
  await expect(page.getByLabel('Nguồn tài liệu')).toHaveValue('public')
  await expect(page.getByLabel('Nguồn tài liệu').locator('option')).toHaveCount(1)
  await expect(page.getByRole('link', { name: 'Tải tài liệu', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Tạo báo cáo', exact: true })).toHaveCount(0)
  await page.goto('/upload')
  await expect(page.getByRole('heading', { name: 'Cần quyền nội bộ' })).toBeVisible()
  expect(reads.every(url => new URL(url).searchParams.get('scope') === 'public')).toBe(true)
})

test('login and logout change access and clear the private conversation', async ({ page, context, faults }) => {
  let internal = false
  await intercept(context, `${API}/auth/session`, route => ok(route, { private_access: internal, private_configured: true }))
  await intercept(context, `${API}/auth/login`, async route => { internal = true; await ok(route, { private_access: true }) })
  await intercept(context, `${API}/auth/logout`, async route => { internal = false; await ok(route, { private_access: false }) })
  await intercept(context, `${API}/chat`, route => ok(route, { answer: 'PRIVATE_CONVERSATION_CANARY [S1]', sources: [{ ...sources[0], scope: 'private' }], coverage }))
  await page.goto('/chat')
  await page.getByRole('button', { name: 'Đăng nhập nội bộ', exact: true }).click()
  await page.getByLabel('Khóa truy cập', { exact: true }).fill('sample-internal-token-for-browser-test')
  await page.getByRole('button', { name: 'Mở không gian nội bộ', exact: true }).click()
  await expect(page.getByLabel('Nguồn tài liệu')).toHaveValue('private')
  await page.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Nội dung nội bộ?')
  await page.getByRole('button', { name: 'Gửi', exact: true }).click()
  await expect(page.locator('article')).toContainText('PRIVATE_CONVERSATION_CANARY')
  await page.getByRole('button', { name: 'Đăng xuất', exact: true }).click()
  await expect(page.getByLabel('Nguồn tài liệu')).toHaveValue('public')
  await expect(page.locator('article')).toHaveCount(0)
  expect(await page.evaluate(() => JSON.stringify(localStorage)+JSON.stringify(sessionStorage))).not.toContain('sample-internal-token')
})

test('public answers block generated private and external links and mismatched sources', async ({ page, context, faults }) => {
  await intercept(context, `${API}/auth/session`, route => ok(route, { private_access: false, private_configured: true }))
  let count = 0
  await intercept(context, `${API}/chat`, async route => {
    count++
    if (count === 1) return ok(route, { answer: '[Mở private](/documents/secret?scope=private) và [Trang lạ](https://untrusted.example/collect) [S1]', sources, coverage })
    return ok(route, { answer: 'SHOULD_NEVER_RENDER', sources: [{ ...sources[0], scope: 'private' }], coverage })
  })
  await page.goto('/chat')
  await page.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Thử link')
  await page.getByRole('button', { name: 'Gửi', exact: true }).click()
  await expect(page.locator('article')).toContainText('Mở private')
  await expect(page.locator('article a')).toHaveCount(0)
  await page.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Thử sai kho')
  await page.getByRole('button', { name: 'Gửi', exact: true }).click()
  await expect(page.locator('article').last()).toContainText('Đã chặn kết quả')
  await expect(page.getByText('SHOULD_NEVER_RENDER')).toHaveCount(0)
})

test('desktop overview and chat keep a balanced layout', async ({ page, faults }) => {
  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Tri thức của bạn, trong tầm tay.' })).toBeVisible()
  await page.screenshot({ path: 'test-results/overview-desktop.png', fullPage: true })
  await page.getByRole('link', { name: 'Hỏi đáp', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Bạn muốn tìm hiểu điều gì?' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/chat-desktop.png', fullPage: true })
})

test('logout clears private conversations in other open tabs', async ({ page, context, faults }) => {
  let internal = true
  await intercept(context, `${API}/auth/session`, route => ok(route, { private_access: internal, private_configured: true }))
  await intercept(context, `${API}/auth/logout`, async route => { internal = false; await ok(route, { private_access: false }) })
  await intercept(context, `${API}/chat`, route => ok(route, { answer: 'PRIVATE_OTHER_TAB [S1]', sources: [{ ...sources[0], scope: 'private' }], coverage }))
  await page.goto('/chat')
  const second = await context.newPage()
  second.on('pageerror', error => faults.push(error.message))
  await second.goto('/chat')
  await second.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Riêng tư')
  await second.getByRole('button', { name: 'Gửi', exact: true }).click()
  await expect(second.locator('article')).toContainText('PRIVATE_OTHER_TAB')
  await page.getByRole('button', { name: 'Đăng xuất', exact: true }).click()
  await expect(second.getByLabel('Nguồn tài liệu')).toHaveValue('public')
  await expect(second.locator('article')).toHaveCount(0)
  await second.close()
})

test('session outage blocks workspace and reconnect restores public access', async ({ page, context, faults }) => {
  let recovered = false
  const reads: string[] = []
  await intercept(context, `${API}/auth/session`, route => recovered ? ok(route, { private_access:false, private_configured:true }) : fail(route, 503, 'Temporary outage'))
  await intercept(context, `${API}/documents/paged*`, async route => { reads.push(route.request().url()); await route.fallback() })
  await page.goto('/chat')
  await expect(page.getByRole('heading', { name:'Chưa kết nối được máy chủ' })).toBeVisible()
  expect(reads).toEqual([])
  await expect(page.getByRole('button', { name:'Đăng nhập nội bộ' })).toHaveCount(0)
  recovered = true
  await page.getByRole('button', { name:'Kết nối lại', exact:true }).click()
  await expect(page.getByLabel('Nguồn tài liệu')).toHaveValue('public')
  expect(reads.length).toBeGreaterThan(0)
  expect(reads.every(url => new URL(url).searchParams.get('scope') === 'public')).toBe(true)
})

test('missing model blocks submission and recovery retains the question', async ({ page, context, faults }) => {
  let ready = false, calls = 0
  await intercept(context, `${API}/chat/models`, route => ok(route, [
    { id:'qwen2.5:7b', label:'Qwen 2.5 · 7B', configured:true, ready, message:'Máy chủ chưa tải mô hình trả lời này.' },
    { id:'llama3.1:70b', label:'Llama 3.1 · 70B', configured:true, ready:false },
    { id:'openai', label:'OpenAI', configured:false, ready:false },
  ]))
  await intercept(context, `${API}/chat`, async route => { calls++; await ok(route, { answer:'Đã phục hồi', sources:[], coverage }) })
  await page.goto('/chat')
  await expect(page.getByRole('alert')).toContainText('Máy chủ chưa tải mô hình')
  await page.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Giữ lại câu hỏi này')
  await expect(page.getByRole('button', { name:'Gửi', exact:true })).toBeDisabled()
  await page.locator('form').evaluate(form => form.dispatchEvent(new Event('submit', { bubbles:true, cancelable:true })))
  expect(calls).toBe(0)
  ready = true
  await page.getByRole('button', { name:'Kiểm tra lại', exact:true }).click()
  await expect(page.getByRole('button', { name:'Gửi', exact:true })).toBeEnabled()
  await expect(page.getByPlaceholder('Đặt câu hỏi về tài liệu...')).toHaveValue('Giữ lại câu hỏi này')
  await page.getByRole('button', { name:'Gửi', exact:true }).click()
  await expect(page.locator('article')).toContainText('Đã phục hồi')
  expect(calls).toBe(1)
})

test('model inventory outage offers retry without pretending local models are ready', async ({ page, context, faults }) => {
  let recovered = false
  await intercept(context, `${API}/chat/models`, route => recovered ? ok(route, [
    { id:'qwen2.5:7b', label:'Qwen 2.5 · 7B', configured:true, ready:true },
  ]) : fail(route, 503, 'Temporary outage'))
  await page.goto('/chat')
  await page.getByPlaceholder('Đặt câu hỏi về tài liệu...').fill('Câu hỏi chờ kết nối')
  await expect(page.getByRole('alert')).toContainText('Chưa kiểm tra được trạng thái mô hình')
  await expect(page.getByRole('button', { name:'Gửi', exact:true })).toBeDisabled()
  recovered = true
  await page.getByRole('button', { name:'Kiểm tra lại', exact:true }).click()
  await expect(page.getByRole('button', { name:'Gửi', exact:true })).toBeEnabled()
})

test('report uses selected private documents, a custom outline and a local model; shows missing sections', async ({ page, context, faults }) => {
  let calls = 0, payload: any
  await intercept(context, `${API}/report`, async route => {
    calls++; payload=route.request().postDataJSON(); await wait(150)
    await ok(route, { content:'# Tổng hợp\n\n24 tháng [S1].', sources:[{...sources[0],scope:'private'}],
      sections:[{heading:'Bằng chứng',status:'verified',truncated:false},{heading:'Điều kiện',status:'no_evidence',truncated:false}],
      coverage:{ total_sections:2,successful_sections:1,verified_sections:1,verification_enabled:true,evidence_documents:1,unrepresented_document_ids:[],partial:true } })
  })
  await page.goto('/report')
  await page.getByLabel('Tiêu đề', {exact:true}).fill('  Tổng hợp  ')
  await page.getByLabel('Mô hình viết báo cáo').selectOption('llama3.1:70b')
  await expect(page.getByLabel('Mô hình viết báo cáo').locator('option[value=openai]')).toHaveCount(0)
  await page.getByLabel('Dàn ý tùy chọn').fill('Bằng chứng\nĐiều kiện')
  await page.getByLabel('Phạm vi tài liệu').selectOption('selected')
  await expect(page.getByRole('button',{name:'Tạo báo cáo',exact:true})).toBeDisabled()
  await page.getByRole('checkbox',{name:'private.pdf',exact:true}).check()
  await page.locator('form').evaluate(form => { form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})); form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})) })
  await expect(page.getByLabel('Mô hình viết báo cáo')).toBeDisabled()
  await expect(page.getByText(/Đã kiểm chứng 1\/2 mục/)).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('Báo cáo còn phần thiếu')
  await expect(page.locator('article')).not.toContainText('[S1]')
  expect(calls).toBe(1)
  expect(payload).toEqual({template:'technical',title:'Tổng hợp',instructions:'',model:'llama3.1:70b',document_ids:['private-doc'],sections:['Bằng chứng','Điều kiện']})
})

test('report validation and request failures preserve the brief without duplicate requests', async ({ page, context, faults }) => {
  let calls=0
  await intercept(context, `${API}/report`, async route => { calls++; await fail(route,503,'Dịch vụ tạm gián đoạn') })
  await page.goto('/report')
  await page.getByLabel('Tiêu đề',{exact:true}).fill('Báo cáo cần giữ')
  await page.getByLabel('Dàn ý tùy chọn').fill('1\n2\n3\n4\n5')
  await page.getByRole('button',{name:'Tạo báo cáo',exact:true}).click()
  await expect(page.getByRole('alert')).toContainText('tối đa 4 mục')
  expect(calls).toBe(0)
  await page.getByLabel('Dàn ý tùy chọn').fill('Bằng chứng')
  await page.getByRole('button',{name:'Tạo báo cáo',exact:true}).click()
  await expect(page.getByRole('alert')).toContainText('Dịch vụ tạm gián đoạn')
  await expect(page.getByLabel('Tiêu đề',{exact:true})).toHaveValue('Báo cáo cần giữ')
  await expect(page.getByLabel('Dàn ý tùy chọn')).toHaveValue('Bằng chứng')
  expect(calls).toBe(1)
})

test('report download and copy hide codes and block model URLs while preserving trusted references', async ({ page, context, faults }) => {
  await page.addInitScript(() => { Object.defineProperty(navigator,'clipboard',{value:{writeText:(value:string)=>{(window as any).reportCopied=value;return Promise.resolve()}},configurable:true}) })
  await intercept(context,`${API}/report`,route => ok(route,{content:'# Báo cáo\n\n24 tháng [S1]. [Link](https://evil.example/steal)\n\n![Ảnh](https://evil.example/image)',sources:[{...sources[0],scope:'private'}]}))
  await page.goto('/report')
  await page.getByLabel('Tiêu đề',{exact:true}).fill('Báo cáo')
  await page.getByRole('button',{name:'Tạo báo cáo',exact:true}).click()
  await expect(page.locator('article')).toContainText('24 tháng.')
  await page.getByRole('button',{name:'Sao chép báo cáo',exact:true}).click()
  const copied=await page.evaluate(()=>(window as any).reportCopied)
  expect(copied).toContain('24 tháng.')
  expect(copied).not.toContain('[S1]')
  expect(copied).not.toContain('evil.example')
  expect(copied).toContain('scope=private')
  const pending=page.waitForEvent('download')
  await page.getByRole('button',{name:'Tải báo cáo',exact:true}).click()
  const downloaded=await pending
  expect(downloaded.suggestedFilename()).toBe('bao-cao.md')
  await page.setViewportSize({width:390,height:844})
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.screenshot({path:'test-results/report-mobile.png',fullPage:true})
})
