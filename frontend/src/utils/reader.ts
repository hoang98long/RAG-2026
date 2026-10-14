import type { Scope } from '../types'
type ReaderLocation = { valid: true; scope: Scope; chunk: number | null; page: number | null; version?: string; digest?: string }
export function parseReaderLocation(params: URLSearchParams): ReaderLocation | { valid: false; error: string } {
  const scope = params.get('scope') || 'private'
  const parse = (value: string | null, minimum: number) => {
    if (value == null) return null
    if (!/^\d+$/.test(value)) return undefined
    const number = Number(value)
    return Number.isSafeInteger(number) && number >= minimum ? number : undefined
  }
  const chunk = parse(params.get('chunk'), 0), page = parse(params.get('page'), 1)
  const version = params.get('version') || undefined, digest = params.get('digest') || undefined
  if (!['private', 'public'].includes(scope) || chunk === undefined || page === undefined
    || (version && !/^[a-zA-Z0-9_-]{1,100}$/.test(version))
    || (digest && (!/^[a-f0-9]{16}$/.test(digest) || chunk == null))) {
    return { valid: false, error: 'Liên kết tài liệu không hợp lệ. Hãy mở lại từ nguồn tham chiếu.' }
  }
  return { valid: true, scope: scope as Scope, chunk, page, version, digest }
}
export function readerRequest(location: ReaderLocation, offset: number | null) {
  const includesSource = offset == null || (location.chunk != null && location.chunk >= offset && location.chunk < offset + 50)
  return { scope: location.scope, version: location.version, offset: offset ?? 0, limit: 50,
    ...(includesSource ? { chunk: location.chunk ?? undefined, page: location.page ?? undefined, digest: location.digest } : {}) }
}
