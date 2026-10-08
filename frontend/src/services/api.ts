import axios from 'axios'
import type { ApiResponse, Document, Source } from '../types'
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' })
export const getDocuments = () => api.get<ApiResponse<Document[]>>('/documents').then(r => r.data.data)
export const getDashboard = () => api.get<ApiResponse<{documents:number;chats:number;reports:number}>>('/dashboard').then(r => r.data.data)
export const uploadDocuments = async (files: File[], onProgress: (n: number) => void, onUploaded?: (file: File) => void) => {
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0) || 1
  let completedBytes = 0
  for (const file of files) {
    const form = new FormData()
    form.append('files', file)
    await api.post('/documents/upload', form, { timeout: 0, onUploadProgress: event => {
      const ratio = Math.min(event.loaded / (event.total || Math.max(file.size, 1)), 1)
      onProgress(Math.round((completedBytes + file.size * ratio) * 100 / totalBytes))
    } })
    completedBytes += file.size
    onUploaded?.(file)
    onProgress(Math.round(completedBytes * 100 / totalBytes))
  }
}
export const deleteDocument = (id: string) => api.delete(`/documents/${id}`)
export const askChat = (question: string) => api.post<ApiResponse<{answer:string;sources:Source[]}>>('/chat', { question }).then(r => r.data.data)
export const createReport = (data: {template:string;title:string;instructions:string}) => api.post<ApiResponse<{content:string;sources:Source[]}>>('/report', data).then(r => r.data.data)

export const getDocumentContent = (id: string, params: { offset?: number; limit?: number; chunk?: number; page?: number } = {}) => api.get<ApiResponse<import('../types').DocumentContent>>(`/documents/${encodeURIComponent(id)}/content`, { params }).then(r => r.data.data)
export const documentFileUrl = (id: string, page?: number | null) => `${api.defaults.baseURL?.replace(/\/$/, '')}/documents/${encodeURIComponent(id)}/file${page != null ? `#page=${page}` : ''}`

export const getUploadLimits = () => api.get<ApiResponse<{ max_file_mb: number; max_request_mb: number; max_files: number }>>('/documents/upload-limits').then(r => r.data.data)

export const getDocumentPage = (offset = 0, limit = 50) => api.get<ApiResponse<{ items: Document[]; total: number; offset: number; limit: number }>>('/documents/paged', { params: { offset, limit } }).then(r => r.data.data)
