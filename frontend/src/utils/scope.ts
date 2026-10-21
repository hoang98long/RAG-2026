import type { ChatScope, Source } from '../types'

export class ScopeViolation extends Error { constructor() { super('Scope violation'); this.name = 'ScopeViolation' } }

export function validateSources(value: unknown, scope: ChatScope): Source[] {
  if (!Array.isArray(value) || value.some(item => !item || typeof item !== 'object' ||
    typeof item.document !== 'string' || typeof item.content !== 'string' ||
    !['private', 'public'].includes(item.scope) || (scope !== 'all' && item.scope !== scope))) {
    throw new ScopeViolation()
  }
  return value as Source[]
}
