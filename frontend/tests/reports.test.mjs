import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import test from 'node:test'
import ts from 'typescript'
import { fromMarkdown } from 'mdast-util-from-markdown'
const require = createRequire(import.meta.url)
const transpile = source => ts.transpileModule(source, { compilerOptions:{ module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2020 } }).outputText
const sourceCode = transpile(readFileSync(new URL('../src/utils/sources.ts',import.meta.url),'utf8'))
const sourceModule = `data:text/javascript;base64,${Buffer.from(sourceCode).toString('base64')}`
let code = transpile(readFileSync(new URL('../src/utils/reportExport.ts',import.meta.url),'utf8')).replace("from './sources'",`from '${sourceModule}'`)
for (const name of ['mdast-util-from-markdown','mdast-util-to-markdown']) code = code.replace(`from '${name}'`,`from '${pathToFileURL(require.resolve(name)).href}'`)
const { reportMarkdown } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const source = { scope:'private',document_id:'doc',document:'A.pdf',chunk_index:53,page:7,index_version:'documents_v5_test',digest:'0123456789abcdef',content:'Fact' }
const walk = (node, result=[]) => { result.push(node); node.children?.forEach(child => walk(child,result)); return result }

test('report export removes citation markers from prose and preserves literal code', () => {
  const result = reportMarkdown('# Title\n\n24 months [S1, S2].\n\n`[S1]`\n\n```text\n[S3]\n```',[],'https://app.example')
  assert.ok(result.startsWith('# Title'))
  assert.match(result,/24 months\./)
  assert.match(result,/`\[S1\]`/)
  assert.match(result,/\[S3\]/)
  assert.doesNotMatch(result,/S2/)
})

test('report export removes model links, reference destinations, remote images and raw HTML', () => {
  const result = reportMarkdown('[Open](https://evil.example/steal) [Ref][r]\n\n[r]: https://evil.example/ref\n\n![Remote](https://evil.example/image)\n\n<script>evil()</script>',[source],'https://app.example')
  const nodes = walk(fromMarkdown(result))
  assert.equal(nodes.filter(node => node.type==='image'||node.type==='html'||node.type==='definition').length,0)
  const links = nodes.filter(node => node.type==='link')
  assert.equal(links.length,1)
  assert.equal(new URL(links[0].url).origin,'https://app.example')
  assert.doesNotMatch(result,/evil\.example/)
})

test('report source links preserve scope, fingerprint, page and chunk without code labels', () => {
  const result = reportMarkdown('Fact [S1]',[source],'https://app.example')
  const link = walk(fromMarkdown(result)).find(node => node.type==='link')
  const url = new URL(link.url)
  assert.equal(url.searchParams.get('scope'),'private')
  assert.equal(url.searchParams.get('chunk'),'53')
  assert.equal(url.searchParams.get('page'),'7')
  assert.equal(url.searchParams.get('digest'),'0123456789abcdef')
  assert.doesNotMatch(result,/\[S1\]/)
})

test('untrusted filenames remain text in the reference link', () => {
  const result = reportMarkdown('Fact [S1]',[{...source,document:'[Open](https://evil.example) <img src=x>'}],'https://app.example')
  const nodes = walk(fromMarkdown(result))
  assert.equal(nodes.filter(node => node.type==='link').length,1)
  assert.equal(new URL(nodes.find(node => node.type==='link').url).origin,'https://app.example')
  assert.equal(nodes.filter(node => node.type==='html'||node.type==='image').length,0)
})
