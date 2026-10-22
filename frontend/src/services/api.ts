import axios from 'axios'
import { validateSources, ScopeViolation } from '../utils/scope'
import type { ApiResponse, Document, Source, Scope, ChatScope, ChatModel, ChatMode, DirectChatMessage, Coverage } from '../types'
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '/api', timeout: 20000, withCredentials: true })
api.interceptors.response.use(response => response, error => {
  if (error.response?.status === 401 && typeof window !== 'undefined') window.dispatchEvent(new Event('documind-access-expired'))
  return Promise.reject(error)
})
const configuredTimeout = Number(import.meta.env.VITE_AI_TIMEOUT_MS)
const aiTimeout = Number.isFinite(configuredTimeout) && configuredTimeout > 0 ? configuredTimeout : 600000
function payload<T>(value: ApiResponse<T>): T {
  if (!value || value.success !== true || value.data == null) throw new Error('Dịch vụ trả về kết quả chưa hợp lệ.')
  return value.data
}
export const getDocuments = (scope: Scope = 'private', signal?: AbortSignal) => api.get<ApiResponse<Document[]>>('/documents', { params: { scope }, signal }).then(r => payload(r.data))
export const getDashboard = (scope: Scope = 'private', signal?: AbortSignal) => api.get<ApiResponse<{documents:number;chats:number;reports:number}>>('/dashboard', { params: { scope }, signal }).then(r => payload(r.data))
export const uploadDocuments = async (files: File[], onProgress: (n: number) => void, onUploaded?: (file: File) => void, scope: Scope = 'private', requestId?: (file: File) => string) => {
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0) || 1
  let completedBytes = 0
  for (const file of files) {
    const form = new FormData()
    form.append('files', file)
    const response = await api.post<ApiResponse<Document[]>>('/documents/upload', form, { timeout: 0, params: { scope }, headers: requestId ? { 'Idempotency-Key': requestId(file) } : undefined, onUploadProgress: event => {
      const ratio = Math.min(event.loaded / (event.total || Math.max(file.size, 1)), 1)
      onProgress(Math.round((completedBytes + file.size * ratio) * 100 / totalBytes))
    } })
    payload(response.data)
    completedBytes += file.size
    onUploaded?.(file)
    onProgress(Math.round(completedBytes * 100 / totalBytes))
  }
}
export const deleteDocument = (id: string, scope: Scope = 'private') => api.delete(`/documents/${encodeURIComponent(id)}`, { params: { scope } })
export const askChat = (question: string, model: ChatModel = 'qwen2.5:7b', scope: ChatScope = 'private', signal?: AbortSignal) => api.post<ApiResponse<{answer:string;sources:Source[];coverage:Coverage}>>('/chat', { question, model, scope }, { timeout: aiTimeout, signal }).then(r => {
  const result = payload(r.data)
  if (typeof result.answer !== 'string' || !Array.isArray(result.sources)) throw new Error('Câu trả lời nhận được chưa hợp lệ.')
  return { ...result, sources: validateSources(result.sources, scope) }
})
export const askDirectChat = (messages: DirectChatMessage[], signal?: AbortSignal, pdf?: File | null) => {
  const form = pdf ? new FormData() : null
  if (form && pdf) { form.append('messages', JSON.stringify({ messages })); form.append('file', pdf) }
  return api.post<ApiResponse<{answer:string;sources:Source[];mode:'direct';model:'openai'}>>(pdf ? '/chat/direct/pdf' : '/chat/direct', form || { messages }, { timeout: aiTimeout, signal }).then(r => {
  const result = payload(r.data)
  if (typeof result.answer !== 'string' || !result.answer.trim() || result.mode !== 'direct' ||
      !Array.isArray(result.sources) || result.sources.length) throw new Error('Câu trả lời trực tiếp nhận được chưa hợp lệ.')
  return result
  })
}
export const getChatModels = (signal?: AbortSignal, mode: ChatMode = 'rag') => api.get<ApiResponse<{id:ChatModel;label:string;configured:boolean;ready?:boolean;reason?:string;message?:string}[]>>('/chat/models', { signal, params: mode === 'direct' ? { mode } : undefined }).then(r => payload(r.data))
export const createReport = (data: {template:string;title:string;instructions:string;model?:'qwen2.5:7b'|'llama3.1:70b';document_ids?:string[];sections?:string[]}, signal?: AbortSignal) => api.post<ApiResponse<import('../types').ReportResult>>('/report', data, { timeout: aiTimeout, signal }).then(r => { const result = payload(r.data); return { ...result, sources: validateSources(result.sources, 'private') } })

export const getDocumentContent = (id: string, params: { offset?: number; limit?: number; chunk?: number; page?: number; scope?: Scope; version?: string; digest?: string } = {}, signal?: AbortSignal) => api.get<ApiResponse<import('../types').DocumentContent>>(`/documents/${encodeURIComponent(id)}/content`, { params, signal }).then(r => { const result = payload(r.data); if (result.scope !== (params.scope || 'private')) throw new ScopeViolation(); return result })
export const documentFileUrl = (id: string, page?: number | null, scope: Scope = 'private') => `${api.defaults.baseURL?.replace(/\/$/, '')}/documents/${encodeURIComponent(id)}/file?scope=${scope}${page != null ? `#page=${page}` : ''}`
export const getUploadLimits = (signal?: AbortSignal) => api.get<ApiResponse<{ max_file_mb: number; max_request_mb: number; max_files: number }>>('/documents/upload-limits', { signal }).then(r => payload(r.data))
export const getDocumentPage = (offset = 0, limit = 50, scope: Scope = 'private', signal?: AbortSignal, search = '') => api.get<ApiResponse<{ items: Document[]; total: number; offset: number; limit: number }>>('/documents/paged', { params: { offset, limit, scope, ...(search ? { q:search } : {}) }, signal }).then(r => { const result = payload(r.data); if (!Array.isArray(result.items) || result.items.some(item => item.scope !== scope)) throw new ScopeViolation(); return result })

export const getAccessSession = (signal?: AbortSignal) => api.get<ApiResponse<{private_access:boolean;private_configured:boolean}>>('/auth/session', { signal }).then(r => payload(r.data))
export const loginPrivate = (token: string) => api.post('/auth/login', { token })
export const logoutPrivate = () => api.post('/auth/logout')
