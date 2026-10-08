import type { Source } from '../types'

export function sourceUrl(source: Source): string | undefined {
  if (!source.document_id) return undefined
  const params = new URLSearchParams()
  if (source.chunk_index != null) params.set('chunk', String(source.chunk_index))
  if (source.page != null) params.set('page', String(source.page))
  return `/documents/${encodeURIComponent(source.document_id)}?${params}`
}

type MarkdownNode = { type: string; value?: string; url?: string; children?: MarkdownNode[] }

// Transform text nodes only, preserving code blocks and existing Markdown links.
export function citationLinks(sources: Source[]) {
  const byId = new Map(sources.map((source, index) => [source.source_id || `S${index + 1}`, source]))
  return () => (tree: MarkdownNode) => {
    const visit = (node: MarkdownNode) => {
      if (!node.children || ['link', 'linkReference', 'code', 'inlineCode'].includes(node.type)) return
      node.children = node.children.flatMap(child => {
        if (child.type !== 'text' || !child.value) { visit(child); return [child] }
        const parts: MarkdownNode[] = []
        const text = child.value
        let start = 0
        for (const match of text.matchAll(/\[(S\d+)\]/g)) {
          const source = byId.get(match[1])
          const url = source && sourceUrl(source)
          if (!url || match.index == null) continue
          if (match.index > start) parts.push({ type: 'text', value: text.slice(start, match.index) })
          parts.push({ type: 'link', url, children: [{ type: 'text', value: match[0] }] })
          start = match.index + match[0].length
        }
        if (!parts.length) return [child]
        if (start < text.length) parts.push({ type: 'text', value: text.slice(start) })
        return parts
      })
    }
    visit(tree)
  }
}
