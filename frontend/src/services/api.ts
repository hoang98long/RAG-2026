import axios from 'axios'
import type { ApiResponse, Document, Source } from '../types'
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000' })
export const getDocuments = () => api.get<ApiResponse<Document[]>>('/documents').then(r => r.data.data)
export const getDashboard = () => api.get<ApiResponse<{documents:number;chats:number;reports:number}>>('/dashboard').then(r => r.data.data)
export const uploadDocuments = (files: File[], onProgress: (n:number) => void) => { const form = new FormData(); files.forEach(f => form.append('files', f)); return api.post('/documents/upload', form, { onUploadProgress: e => onProgress(Math.round((e.loaded * 100) / (e.total || 1))) }) }
export const deleteDocument = (id: string) => api.delete(`/documents/${id}`)
export const askChat = (question: string) => api.post<ApiResponse<{answer:string;sources:Source[]}>>('/chat', { question }).then(r => r.data.data)
export const createReport = (data: {template:string;title:string;instructions:string}) => api.post<ApiResponse<{content:string;sources:Source[]}>>('/report', data).then(r => r.data.data)

export const getDocumentContent = (id: string) => api.get<ApiResponse<import('../types').DocumentContent>>(`/documents/${encodeURIComponent(id)}/content`).then(r => r.data.data)
export const documentFileUrl = (id: string, page?: number | null) => `${api.defaults.baseURL?.replace(/\/$/, '')}/documents/${encodeURIComponent(id)}/file${page != null ? `#page=${page}` : ''}`
