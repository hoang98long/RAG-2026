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

export function chatErrorMessage(error: unknown): string {
  const unavailable = 'Chưa thể nhận câu trả lời lúc này. Vui lòng thử lại sau.'
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    if (status === 429) {
      const seconds = Number(error.response?.headers?.['retry-after'])
      return Number.isFinite(seconds) && seconds > 0 && seconds <= 3600
        ? `Có nhiều yêu cầu cùng lúc. Vui lòng thử lại sau ${Math.ceil(seconds)} giây.`
        : 'Có nhiều yêu cầu cùng lúc. Vui lòng thử lại sau.'
    }
    if (status && status >= 500) return unavailable
    if (status === 401) return 'Phiên truy cập đã hết hạn. Vui lòng đăng nhập lại.'
    if (status === 403) return 'Bạn không có quyền sử dụng tài liệu này.'
    if (status === 413 && /PDF/i.test(String(error.response?.data?.detail || ''))) return 'PDF vượt giới hạn cho phép. Hãy chọn tệp nhỏ hơn.'
    if (status === 413) return 'Nội dung quá dài. Hãy rút ngắn tin nhắn và thử lại.'
    if (status === 422) return 'Vui lòng kiểm tra lại nội dung vừa nhập.'
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') return 'Phản hồi mất nhiều thời gian. Bạn hãy thử lại hoặc rút ngắn câu hỏi.'
    if (!error.response) return 'Không thể kết nối. Vui lòng kiểm tra mạng và thử lại.'
  }
  return errorMessage(error, unavailable)
}

export function retryRead(failureCount: number, error: unknown): boolean {
  if (axios.isCancel(error) || (error instanceof Error && error.name === 'ScopeViolation')) return false
  const status = axios.isAxiosError(error) ? error.response?.status : undefined
  if (status && status >= 400 && status < 500 && status !== 408 && status !== 429) return false
  return failureCount < 1
}
