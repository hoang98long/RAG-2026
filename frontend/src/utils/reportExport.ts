import { fromMarkdown } from 'mdast-util-from-markdown'
import { toMarkdown } from 'mdast-util-to-markdown'
import { sourceUrl } from './sources'
import type { Source } from '../types'

type Node = { type: string; value?: string; alt?: string; children?: Node[]; [key: string]: unknown }

/** Export the displayed prose and trusted source links; preserve literal code examples. */
export function reportMarkdown(content: string, sources: Source[], origin: string): string {
  const tree = fromMarkdown(content)
  const clean = (node: Node): Node[] => {
    if (node.type === 'html' || node.type === 'definition') return []
    if (node.type === 'code' || node.type === 'inlineCode') return [node]
    if (node.type === 'image' || node.type === 'imageReference') return [{ type:'text', value:node.alt || '' }]
    if (node.type === 'text' && node.value) node.value = node.value.replace(/[ \t]*\[\s*S\d+(?:\s*[,;]\s*S\d+)*\s*\]/gi, '')
    if (node.children) node.children = node.children.flatMap(clean)
    // Model-provided destinations never become active links in a downloaded report.
    if (node.type === 'link' || node.type === 'linkReference') return node.children || []
    return [node]
  }
  clean(tree as unknown as Node)
  const references = sources.flatMap(source => {
    const href = sourceUrl(source)
    if (!href) return []
    const url = new URL(href, origin)
    if (url.origin !== new URL(origin).origin) return []
    const label = `${source.document}${source.page != null ? ` · Trang ${source.page}` : ''}${source.chunk_index != null ? ` · Đoạn ${source.chunk_index+1}` : ''}`
    return [{ type:'listItem' as const, spread:false, children:[{ type:'paragraph' as const,
      children:[{ type:'link' as const, url:url.href, children:[{ type:'text' as const, value:label }] }] }] }]
  })
  if (references.length) tree.children.push({ type:'heading', depth:2, children:[{ type:'text', value:'Nguồn tham chiếu' }] }, { type:'list', ordered:false, spread:false, children:references })
  return toMarkdown(tree)
}
