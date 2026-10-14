export type Scope = 'private' | 'public'
export type ChatScope = Scope | 'all'
export type ChatModel = 'qwen2.5:7b' | 'llama3.1:70b' | 'openai'
export type Coverage = { exhaustive_requested: boolean; truncated: boolean; completeness_unverified: boolean; evidence_chunks: number; query_count: number; query_planning_fallback: boolean }
export type Document = { id: string; filename: string; upload_time: string; scope?: Scope }
export type Source = { scope?: Scope; index_version?: string; digest?: string; document: string; content: string; source_id?: string; document_id?: string; page?: number | null; chunk_index?: number; score?: number; similarity?: number | null; section?: string; table_header?: string; rerank_score?: number; rerank_method?: string }
export type ApiResponse<T> = { success: boolean; message: string; data: T }

export type DocumentContent = {
  id: string
  filename: string
  file_type: string
  scope?: Scope
  total: number
  offset: number
  limit: number
  target_found: boolean | null
  chunks: { content: string; chunk_index: number; page: number | null }[]
}
