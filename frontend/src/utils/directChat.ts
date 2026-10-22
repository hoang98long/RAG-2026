import type { DirectChatMessage } from '../types'

export const DIRECT_PDF_MAX_BYTES = 10 * 1024 * 1024

export function directPdfError(file: Pick<File, 'name' | 'size' | 'type'>): string | undefined {
  if (!file.name.toLowerCase().endsWith('.pdf') || (file.type && !['application/pdf', 'application/octet-stream'].includes(file.type)))
    return 'Chỉ hỗ trợ tệp PDF.'
  if (!file.size) return 'Tệp PDF đang trống. Hãy chọn tệp khác.'
  if (file.size > DIRECT_PDF_MAX_BYTES) return 'PDF tối đa 10 MB. Hãy chọn tệp nhỏ hơn.'
  return undefined
}

const encoder = new TextEncoder()

function fits(messages: DirectChatMessage[]): boolean {
  return messages.length <= 21 && messages.every(item => item.content.length <= 12000) &&
    messages.reduce((total, item) => total + encoder.encode(item.content).length, 0) <= 48000 &&
    encoder.encode(JSON.stringify({ messages })).length <= 60000
}

export function buildDirectConversation(history: DirectChatMessage[], question: string) {
  let messages: DirectChatMessage[] = [{ role: 'user', content: question.trim() }]
  if (!messages[0].content || !fits(messages)) throw new Error('Tin nhắn quá dài. Hãy rút ngắn nội dung trước khi gửi.')
  // Keep complete recent exchanges; never insert an error bubble or a RAG message.
  for (let index = history.length - 2; index >= 0; index -= 2) {
    const pair = history.slice(index, index + 2)
    if (pair[0].role !== 'user' || pair[1].role !== 'assistant') break
    const candidate = [...pair, ...messages]
    if (!fits(candidate)) break
    messages = candidate
  }
  return { messages, trimmed: history.length > messages.length - 1 }
}
