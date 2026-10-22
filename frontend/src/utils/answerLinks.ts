import type { Source } from '../types'
import { sourceUrl } from './sources'

export function allowedDirectLink(href: string | undefined, origin: string): string | undefined {
  if (!href) return undefined
  try {
    const target = new URL(href)
    if (!['https:', 'http:'].includes(target.protocol) || target.origin === origin ||
        target.username || target.password) return undefined
    return target.href
  } catch { return undefined }
}

export function allowedAnswerLink(href: string | undefined, sources: Source[], origin: string): string | undefined {
  if (!href) return undefined
  try {
    const target = new URL(href, origin)
    if (target.origin !== origin || target.username || target.password) return undefined
    return sources.some(source => { const url = sourceUrl(source); return url && new URL(url, origin).href === target.href }) ? target.href : undefined
  } catch { return undefined }
}
