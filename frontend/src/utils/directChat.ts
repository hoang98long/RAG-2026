import type { DirectChatMessage } from '../types'

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
