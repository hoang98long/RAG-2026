export type Document = { id: string; filename: string; upload_time: string }
export type Source = { document: string; content: string; source_id?: string; document_id?: string; page?: number | null; chunk_index?: number; score?: number; similarity?: number | null }
export type ApiResponse<T> = { success: boolean; message: string; data: T }
