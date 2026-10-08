import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/utils/sources.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } })
const { sourceUrl, citationLinks, hideCitationMarkers } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
const sources = [{ source_id: 'S1', document_id: 'document-a', chunk_index: 0, page: 2 }]

test('source link preserves zero-based chunk and one-based page', () => {
  assert.equal(sourceUrl(sources[0]), '/documents/document-a?chunk=0&page=2')
  assert.equal(sourceUrl({}), undefined)
})

test('citations become document links without changing unknown citations', () => {
  const tree = { type: 'root', children: [{ type: 'paragraph', children: [{ type: 'text', value: 'Fact [S1], unknown [S9].' }] }] }
  citationLinks(sources)()(tree)
  assert.deepEqual(tree.children[0].children, [
    { type: 'text', value: 'Fact ' },
    { type: 'link', url: '/documents/document-a?chunk=0&page=2', children: [{ type: 'text', value: '[S1]' }] },
    { type: 'text', value: ', unknown [S9].' },
  ])
})

test('code and existing links keep their original text', () => {
  const tree = { type: 'root', children: [
    { type: 'code', value: '[S1]' },
    { type: 'paragraph', children: [
      { type: 'inlineCode', value: '[S1]' },
      { type: 'link', url: 'https://example.org', children: [{ type: 'text', value: '[S1]' }] },
    ] },
  ] }
  const original = structuredClone(tree)
  citationLinks(sources)()(tree)
  assert.deepEqual(tree, original)
})

test('each message resolves its own source ids', () => {
  const tree = { type: 'root', children: [{ type: 'text', value: '[S1]' }] }
  citationLinks([{ source_id: 'S1', document_id: 'document-b', chunk_index: 9 }])()(tree)
  assert.equal(tree.children[0].url, '/documents/document-b?chunk=9')
})

test('answer prose hides single, adjacent and grouped internal citations', () => {
  const tree = { type: 'root', children: [{ type: 'paragraph', children: [
    { type: 'text', value: 'Code G20 [S1, S2, S4]. Code G21 [S1] [S2]. Other [ S3 ; S9 ].' },
  ] }] }
  hideCitationMarkers()(tree)
  assert.equal(tree.children[0].children[0].value, 'Code G20. Code G21. Other.')
})

test('hiding citations preserves code, links and ordinary brackets', () => {
  const tree = { type: 'root', children: [
    { type: 'code', value: '[S1]' },
    { type: 'paragraph', children: [
      { type: 'inlineCode', value: '[S1]' },
      { type: 'link', url: '/documents/document-a?chunk=0', children: [{ type: 'text', value: '[S1]' }] },
      { type: 'text', value: 'ICD [G20] and [Section 1].' },
    ] },
  ] }
  const original = structuredClone(tree)
  hideCitationMarkers()(tree)
  assert.deepEqual(tree, original)
})
