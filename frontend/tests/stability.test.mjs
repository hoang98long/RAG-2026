import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import test from 'node:test'
import ts from 'typescript'
const require = createRequire(import.meta.url)
async function moduleFrom(path) {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8')
  let { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } })
  outputText = outputText.replace("from 'axios'", `from '${pathToFileURL(require.resolve('axios')).href}'`)
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
}
const { parseReaderLocation, readerRequest } = await moduleFrom('../src/utils/reader.ts')
const { uploadRequestId } = await moduleFrom('../src/utils/uploadId.ts')
const { errorMessage, retryRead } = await moduleFrom('../src/utils/errors.ts')
const axios = require('axios')

test('reader rejects invalid scopes, unsafe indices and incomplete fingerprints', () => {
  for (const query of ['scope=typo', 'chunk=-1', 'page=0', 'chunk=99999999999999999999', 'digest=0123456789abcdef', 'chunk=1&digest=bad']) {
    assert.equal(parseReaderLocation(new URLSearchParams(query)).valid, false, query)
  }
  assert.equal(parseReaderLocation(new URLSearchParams('scope=public&chunk=0')).valid, true)
})

test('pagination always checks fingerprint on the source page', () => {
  const location = parseReaderLocation(new URLSearchParams('scope=public&chunk=53&page=7&version=documents_v5_test&digest=0123456789abcdef'))
  assert.equal(location.valid, true)
  assert.equal(readerRequest(location, null).digest, '0123456789abcdef')
  assert.equal(readerRequest(location, 100).digest, undefined)
  assert.equal(readerRequest(location, 50).digest, '0123456789abcdef')
  assert.equal(readerRequest(location, 50).chunk, 53)
})

test('request identifiers work in insecure contexts without randomUUID', () => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'crypto')
  try {
    Object.defineProperty(globalThis, 'crypto', { configurable: true, value: undefined })
    const identifiers = Array.from({ length: 100 }, uploadRequestId)
    assert.equal(new Set(identifiers).size, 100)
    assert.ok(identifiers.every(value => /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value)))
  } finally {
    if (previous) Object.defineProperty(globalThis, 'crypto', previous)
    else delete globalThis.crypto
  }
})

test('4xx and cancelled read requests do not retry; transient failure retries at most once', () => {
  for (const status of [400,403,404,409,422]) {
    const error = new axios.AxiosError('error')
    error.response = { status, data: { detail: 'message' } }
    assert.equal(retryRead(0,error),false)
    assert.equal(errorMessage(error),'message')
  }
  assert.equal(retryRead(0,new axios.CanceledError()),false)
  assert.equal(retryRead(0,new axios.AxiosError('network')),true)
  assert.equal(retryRead(1,new axios.AxiosError('network')),false)
})

const { validateSources } = await moduleFrom('../src/utils/scope.ts')
const sourcesCode = ts.transpileModule(readFileSync(new URL('../src/utils/sources.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
const sourcesModuleUrl = `data:text/javascript;base64,${Buffer.from(sourcesCode).toString('base64')}`
const linksCode = ts.transpileModule(readFileSync(new URL('../src/utils/answerLinks.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText.replace("from './sources'", `from '${sourcesModuleUrl}'`)
const { allowedAnswerLink, allowedDirectLink } = await import(`data:text/javascript;base64,${Buffer.from(linksCode).toString('base64')}`)

test('public source decoder rejects private, missing-scope and malformed passages', () => {
  const publicSource = { scope: 'public', document: 'P.pdf', content: 'Public fact' }
  assert.deepEqual(validateSources([publicSource], 'public'), [publicSource])
  for (const invalid of [[{ ...publicSource, scope: 'private' }], [{ ...publicSource, scope: undefined }], [null], null]) {
    assert.throws(() => validateSources(invalid, 'public'))
  }
  assert.equal(validateSources([{ ...publicSource, scope: 'private' }, publicSource], 'all').length, 2)
})

test('generated answer links only open a matching source on the application origin', () => {
  const origin = 'https://documents.example'
  const sources = [{ scope: 'public', document_id: 'p', chunk_index: 0 }]
  assert.equal(allowedAnswerLink('/documents/p?chunk=0&scope=public', sources, origin), origin+'/documents/p?chunk=0&scope=public')
  for (const url of ['/documents/secret?scope=private', '/documents/p?chunk=0&scope=private', 'https://evil.example/collect', 'javascript:alert(1)', '//evil.example/documents/p', '/documents/p?chunk=0&scope=public&secret=extra']) {
    assert.equal(allowedAnswerLink(url, sources, origin), undefined)
  }
})


test('direct chat allows normal web links while blocking executable, credential and app links', () => {
  const origin = 'https://documents.example'
  assert.equal(allowedDirectLink('https://developers.openai.com/api/docs', origin), 'https://developers.openai.com/api/docs')
  for (const href of ['javascript:alert(1)', 'data:text/html,secret', '/documents/private?scope=private',
                      origin+'/api/documents/id/file', '//evil.example/collect', 'https://user:pass@example.com']) {
    assert.equal(allowedDirectLink(href, origin), undefined, href)
  }
})

test('rate limit messages include a bounded retry delay', () => {
  const error = new axios.AxiosError('rate limited')
  error.response = { status:429, data:{ detail:'Máy chủ đang bận.' }, headers:{ 'retry-after':'12' } }
  assert.match(errorMessage(error), /12/)
  error.response.headers['retry-after'] = 'not-a-number'
  assert.equal(errorMessage(error), 'Máy chủ đang bận.')
})
