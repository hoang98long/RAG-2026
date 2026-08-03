export type Document = { id: string; filename: string; upload_time: string }
export type Source = { document: string; content: string }
export type ApiResponse<T> = { success: boolean; message: string; data: T }
