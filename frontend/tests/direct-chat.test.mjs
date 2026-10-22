import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/utils/directChat.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } })
const { buildDirectConversation, directPdfError } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)


test('PDF attachment validation accepts one nonempty PDF and rejects unsafe type and oversize input',()=>{
  const valid={name:'document.PDF',type:'application/pdf',size:123}
  assert.equal(directPdfError(valid),undefined)
  assert.equal(directPdfError({...valid,type:''}),undefined)
  assert.equal(directPdfError({...valid,type:'application/octet-stream'}),undefined)
  for(const invalid of [{...valid,name:'bad.docx'},{...valid,type:'text/html'},{...valid,size:0},{...valid,size:10*1024*1024+1}])
    assert.equal(typeof directPdfError(invalid),'string')
})

test('direct context retains complete recent exchanges without mutating history', () => {
  const history = Array.from({ length: 24 }, (_, index) => Object.freeze({
    role: index % 2 ? 'assistant' : 'user', content: 'message-' + index,
  }))
  const result = buildDirectConversation(Object.freeze(history), ' Next question ')
  assert.equal(result.messages.length, 21)
  assert.deepEqual(result.messages[0], history[4])
  assert.deepEqual(result.messages.at(-1), { role: 'user', content: 'Next question' })
  assert.equal(result.trimmed, true)
  assert.equal(history.length, 24)
  assert.ok(result.messages.every((item, index) => item.role === (index % 2 ? 'assistant' : 'user')))
})

test('direct context accounts for Unicode bytes and drops whole pairs at the size boundary', () => {
  const history = [{ role: 'user', content: 'u'.repeat(1000) }, { role: 'assistant', content: 'ấ'.repeat(10000) }]
  const result = buildDirectConversation(history, 'ấ'.repeat(6000))
  assert.equal(result.messages.length, 1)
  assert.equal(result.trimmed, true)
  const small = buildDirectConversation([{ role: 'user', content: 'Tên tôi là Lan' }, { role: 'assistant', content: 'Chào Lan' }], 'Tên tôi?')
  assert.equal(small.messages.length, 3)
  assert.equal(small.trimmed, false)
})

test('direct context checks serialized request size and individual message limits', () => {
  assert.throws(() => buildDirectConversation([], 'x'.repeat(12001)))
  assert.throws(() => buildDirectConversation([], '\u0001'.repeat(12000)))
  assert.throws(() => buildDirectConversation([], '  '))
  const history = [{ role: 'user', content: 'old' }, { role: 'assistant', content: '\u0001'.repeat(11000) }]
  const result = buildDirectConversation(history, 'new')
  assert.equal(result.trimmed, true)
  assert.equal(result.messages.length, 1)
  assert.ok(new TextEncoder().encode(JSON.stringify({ messages: result.messages })).length <= 60000)
})
