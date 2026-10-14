import axios from 'axios'
import type { ApiResponse, Document, Source, Scope, ChatScope, ChatModel, Coverage } from '../types'
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000', timeout: 20000 })
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
  return result
})
export const getChatModels = (signal?: AbortSignal) => api.get<ApiResponse<{id:ChatModel;label:string;configured:boolean}[]>>('/chat/models', { signal }).then(r => payload(r.data))
export const createReport = (data: {template:string;title:string;instructions:string}, signal?: AbortSignal) => api.post<ApiResponse<{content:string;sources:Source[]}>>('/report', data, { timeout: aiTimeout, signal }).then(r => payload(r.data))

export const getDocumentContent = (id: string, params: { offset?: number; limit?: number; chunk?: number; page?: number; scope?: Scope; version?: string; digest?: string } = {}, signal?: AbortSignal) => api.get<ApiResponse<import('../types').DocumentContent>>(`/documents/${encodeURIComponent(id)}/content`, { params, signal }).then(r => payload(r.data))
export const documentFileUrl = (id: string, page?: number | null, scope: Scope = 'private') => `${api.defaults.baseURL?.replace(/\/$/, '')}/documents/${encodeURIComponent(id)}/file?scope=${scope}${page != null ? `#page=${page}` : ''}`
export const getUploadLimits = (signal?: AbortSignal) => api.get<ApiResponse<{ max_file_mb: number; max_request_mb: number; max_files: number }>>('/documents/upload-limits', { signal }).then(r => payload(r.data))
export const getDocumentPage = (offset = 0, limit = 50, scope: Scope = 'private', signal?: AbortSignal) => api.get<ApiResponse<{ items: Document[]; total: number; offset: number; limit: number }>>('/documents/paged', { params: { offset, limit, scope }, signal }).then(r => payload(r.data))
