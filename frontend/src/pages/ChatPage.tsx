import { FormEvent, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import { Send, FileText, Search, ExternalLink } from 'lucide-react'
import { askChat, getDocumentPage } from '../services/api'
import { citationLinks, sourceUrl } from '../utils/sources'
import type { Source } from '../types'

type Message = { role: 'user' | 'assistant'; text: string; sources?: Source[] }

function SourceLink({ source, index }: { source: Source; index: number }) {
  const url = sourceUrl(source)
  const label = <>[{source.source_id || `S${index + 1}`}] {source.document}{source.page != null && ` · Trang ${source.page}`}{source.chunk_index != null && ` · Đoạn ${source.chunk_index + 1}`}</>
  return url ? <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-start gap-1 text-blue-700 underline decoration-blue-200 underline-offset-2 hover:decoration-blue-700">{label}<ExternalLink size={12} className="mt-0.5 shrink-0" /></a> : <span>{label}</span>
}

export default function ChatPage() {
  const [documentOffset, setDocumentOffset] = useState(0)
  const { data: documentPage } = useQuery({ queryKey: ['documents', 'paged', documentOffset, 50], queryFn: () => getDocumentPage(documentOffset, 50) })
  const docs = documentPage?.items || []
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const scroller = useRef<HTMLDivElement>(null)
  const latest = [...messages].reverse().find(message => message.sources?.length)?.sources || []
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight
  }, [messages, loading])
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
  return <div className="grid items-start gap-5 xl:h-[calc(100dvh-4rem)] xl:grid-cols-[220px_minmax(0,1fr)_280px]">
    <aside className="card max-h-48 overflow-auto p-4 xl:max-h-full"><h2 className="mb-3 flex items-center gap-2 font-semibold"><FileText size={17} />Tài liệu ({documentPage?.total || 0})</h2>{docs.length ? docs.map(doc => <a href={`/documents/${encodeURIComponent(doc.id)}`} target="_blank" rel="noopener noreferrer" key={doc.id} className="mb-2 block truncate rounded-lg bg-slate-50 p-2 text-xs text-slate-600 hover:text-blue-700" title={doc.filename}>{doc.filename}</a>) : <p className="text-sm text-slate-500">Chưa có tài liệu.</p>}{(documentPage?.total || 0) > 50 && <div className="mt-3 flex justify-between text-xs"><button disabled={documentOffset === 0} onClick={() => setDocumentOffset(value => Math.max(0, value - 50))} className="text-blue-700 disabled:text-slate-400">Trước</button><button disabled={documentOffset + 50 >= (documentPage?.total || 0)} onClick={() => setDocumentOffset(value => value + 50)} className="text-blue-700 disabled:text-slate-400">Tiếp</button></div>}</aside>
    <section className="card flex h-[calc(100dvh-14rem)] min-h-[320px] min-w-0 flex-col overflow-hidden md:h-[calc(100dvh-4rem)] xl:h-full xl:min-h-0">
      <header className="shrink-0 border-b p-5"><h1 className="text-xl font-bold">Hỏi đáp với tài liệu</h1><p className="mt-1 text-sm text-slate-500">Câu trả lời được tạo từ các đoạn tài liệu liên quan.</p></header>
      <div ref={scroller} className="min-h-0 flex-1 space-y-5 overflow-auto overscroll-contain p-5">
        {messages.length === 0 && <div className="py-24 text-center text-slate-400"><Search className="mx-auto mb-3" /><p>Nhập câu hỏi để bắt đầu.</p></div>}
        {messages.map((item, index) => <div key={index} className={item.role === 'user' ? 'ml-auto max-w-[80%] break-words rounded-2xl rounded-br-sm bg-blue-600 p-4 text-white' : 'max-w-[90%] break-words rounded-2xl rounded-bl-sm bg-slate-100 p-4'}>
          {item.role === 'assistant' ? <>
            <article className="prose prose-sm max-w-none overflow-x-auto"><ReactMarkdown remarkPlugins={[citationLinks(item.sources || [])]} components={{ a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a> }}>{item.text}</ReactMarkdown></article>
            {!!item.sources?.length && <div className="mt-3 space-y-2 border-t border-slate-200 pt-3 text-xs"><p className="font-semibold text-slate-500">Mở nguồn tham chiếu</p>{item.sources.map((source, sourceIndex) => <div key={source.source_id || sourceIndex}><SourceLink source={source} index={sourceIndex} /></div>)}</div>}
          </> : item.text}
        </div>)}
        {loading && <div className="flex items-center gap-2 text-sm text-slate-400"><span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />Đang tìm kiếm và trả lời...</div>}
      </div>
      <form onSubmit={submit} className="flex shrink-0 gap-2 border-t p-4"><input className="input min-w-0" value={question} onChange={event => setQuestion(event.target.value)} placeholder="Đặt câu hỏi về tài liệu..." /><button disabled={loading} className="btn shrink-0 px-3" aria-label="Gửi"><Send size={18} /></button></form>
    </section>
    <aside className="card max-h-96 overflow-auto p-4 xl:max-h-full"><h2 className="mb-3 font-semibold">Nguồn truy xuất</h2>{latest.length ? latest.map((source, index) => <div className="mb-3 rounded-xl border border-slate-100 p-3" key={source.source_id || index}><p className="mb-2 break-words text-xs font-semibold text-blue-700"><SourceLink source={source} index={index} /></p><p className="line-clamp-6 text-xs leading-5 text-slate-500">{source.content}</p></div>) : <p className="text-sm text-slate-500">Nguồn của câu trả lời gần nhất sẽ hiện tại đây.</p>}</aside>
  </div>
}
