import { FormEvent, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import { Send, FileText, Search } from 'lucide-react'
import { askChat, getDocuments } from '../services/api'
import type { Source } from '../types'

type Message = { role: 'user' | 'assistant'; text: string; sources?: Source[] }

export default function ChatPage() {
  const { data: docs = [] } = useQuery({ queryKey: ['documents'], queryFn: getDocuments })
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const latest = messages[messages.length - 1]?.sources || []
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!question.trim() || loading) return
    const value = question.trim()
    setQuestion('')
    setMessages(items => [...items, { role: 'user', text: value }])
    setLoading(true)
    try {
      const result = await askChat(value)
      setMessages(items => [...items, { role: 'assistant', text: result.answer, sources: result.sources }])
    } catch {
      setMessages(items => [...items, { role: 'assistant', text: 'Không thể kết nối dịch vụ AI. Hãy kiểm tra backend và Ollama.' }])
    } finally { setLoading(false) }
  }
  return <div className="grid gap-5 xl:grid-cols-[220px_minmax(0,1fr)_280px]">
    <aside className="card h-fit p-4"><h2 className="mb-3 flex items-center gap-2 font-semibold"><FileText size={17}/>Tài liệu ({docs.length})</h2>{docs.length ? docs.map(doc => <p key={doc.id} className="mb-2 truncate rounded-lg bg-slate-50 p-2 text-xs text-slate-600">{doc.filename}</p>) : <p className="text-sm text-slate-500">Chưa có tài liệu.</p>}</aside>
    <section className="card flex min-h-[640px] flex-col overflow-hidden">
      <header className="border-b p-5"><h1 className="text-xl font-bold">Hỏi đáp với tài liệu</h1><p className="mt-1 text-sm text-slate-500">Câu trả lời được tạo từ các đoạn tài liệu liên quan.</p></header>
      <div className="flex-1 space-y-5 overflow-auto p-5">{messages.length === 0 && <div className="py-24 text-center text-slate-400"><Search className="mx-auto mb-3"/><p>Nhập câu hỏi để bắt đầu.</p></div>}{messages.map((item, index) => <div key={index} className={item.role === 'user' ? 'ml-auto max-w-[80%] rounded-2xl rounded-br-sm bg-blue-600 p-4 text-white' : 'max-w-[90%] rounded-2xl rounded-bl-sm bg-slate-100 p-4'}>{item.role === 'assistant' ? <article className="prose prose-sm max-w-none"><ReactMarkdown>{item.text}</ReactMarkdown></article> : item.text}</div>)}{loading && <div className="flex items-center gap-2 text-sm text-slate-400"><span className="h-2 w-2 animate-pulse rounded-full bg-blue-500"/>Đang tìm kiếm và trả lời...</div>}</div>
      <form onSubmit={submit} className="flex gap-2 border-t p-4"><input className="input" value={question} onChange={event => setQuestion(event.target.value)} placeholder="Đặt câu hỏi về tài liệu..."/><button className="btn px-3" aria-label="Gửi"><Send size={18}/></button></form>
    </section>
    <aside className="card h-fit p-4"><h2 className="mb-3 font-semibold">Nguồn truy xuất</h2>{latest.length ? latest.map((source: Source, index: number) => <div className="mb-3 rounded-xl border border-slate-100 p-3" key={index}><p className="mb-2 text-xs font-semibold text-blue-700">{source.document}</p><p className="line-clamp-6 text-xs leading-5 text-slate-500">{source.content}</p></div>) : <p className="text-sm text-slate-500">Nguồn của câu trả lời gần nhất sẽ hiện tại đây.</p>}</aside>
  </div>
}
