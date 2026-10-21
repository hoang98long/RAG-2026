import axios from 'axios'

export function errorMessage(error: unknown, fallback = 'Không thể hoàn tất thao tác. Vui lòng thử lại.'): string {
  if (error instanceof Error && error.name === 'ScopeViolation') return 'Đã chặn kết quả có nguồn không đúng phạm vi tài liệu đã chọn.'
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (error.response?.status === 429) {
      const seconds = Number(error.response.headers?.['retry-after'])
      return `${typeof detail === 'string' ? detail : 'Máy chủ đang bận.'}${Number.isFinite(seconds) && seconds > 0 && seconds <= 3600 ? ` Vui lòng thử lại sau ${Math.ceil(seconds)} giây.` : ''}`
    }
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
  if (axios.isCancel(error) || (error instanceof Error && error.name === 'ScopeViolation')) return false
  const status = axios.isAxiosError(error) ? error.response?.status : undefined
  if (status && status >= 400 && status < 500 && status !== 408 && status !== 429) return false
  return failureCount < 1
}
