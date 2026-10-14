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
