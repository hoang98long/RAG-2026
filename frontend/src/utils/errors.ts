import axios from 'axios'

export function errorMessage(error: unknown, fallback = 'Không thể hoàn tất thao tác. Vui lòng thử lại.'): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return 'Dữ liệu gửi chưa hợp lệ. Vui lòng kiểm tra nội dung nhập.'
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') return 'Dịch vụ phản hồi quá lâu. Hãy kiểm tra kết nối hoặc thử câu hỏi ngắn hơn.'
    if (!error.response) return 'Không kết nối được dịch vụ. Hãy kiểm tra mạng và backend.'
    const message = error.response.data?.message
    if (typeof message === 'string') return message
  }
  return fallback
}

export function retryRead(failureCount: number, error: unknown): boolean {
  if (axios.isCancel(error)) return false
  const status = axios.isAxiosError(error) ? error.response?.status : undefined
  if (status && status >= 400 && status < 500 && status !== 408 && status !== 429) return false
  return failureCount < 1
}
