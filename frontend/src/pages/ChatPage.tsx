import { FormEvent, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import axios from 'axios'
import { errorMessage } from '../utils/errors'
import { Send, FileText, Search, ExternalLink } from 'lucide-react'
import { askChat, getDocumentPage, getChatModels } from '../services/api'
import { hideCitationMarkers, sourceUrl } from '../utils/sources'
import type { Source, ChatModel, ChatScope, Scope, Coverage } from '../types'

type Message = { role: 'user' | 'assistant'; text: string; sources?: Source[]; coverage?: Coverage }

function SourceLink({ source }: { source: Source }) {
  const url = sourceUrl(source)
  const label = <>{source.document}{source.scope === 'public' && ' · Public'}{source.page != null && ` · Trang ${source.page}`}{source.chunk_index != null && ` · Đoạn ${source.chunk_index + 1}`}</>
  return url ? <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-start gap-1 text-blue-700 underline decoration-blue-200 underline-offset-2 hover:decoration-blue-700"><span className="min-w-0 break-all">{label}</span><ExternalLink size={12} className="mt-0.5 shrink-0" /></a> : <span>{label}</span>
}

export default function ChatPage() {
  const [model, setModel] = useState<ChatModel>('qwen2.5:7b')
  const [scope, setScope] = useState<ChatScope>('private')
  const [catalogueScope, setCatalogueScope] = useState<Scope>('private')
  const [documentOffset, setDocumentOffset] = useState(0)
  const visibleScope = scope === 'all' ? catalogueScope : scope
  const { data: models, isError: modelsError } = useQuery({ queryKey: ['chat-models'], queryFn: ({ signal }) => getChatModels(signal) })
  const { data: documentPage, isPending: documentsPending, isError: documentsError, refetch: retryDocuments } = useQuery({ queryKey: ['documents', 'paged', visibleScope, documentOffset, 50], queryFn: ({ signal }) => getDocumentPage(documentOffset, 50, visibleScope, signal) })
  const docs = documentPage?.items || []
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const submitting = useRef(false)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])
  const scroller = useRef<HTMLDivElement>(null)
  const latest = [...messages].reverse().find(message => message.role === 'assistant')?.sources || []
  const resetConversation = () => { setMessages([]); setQuestion(''); setDocumentOffset(0) }
  const changeModel = (value: ChatModel) => { setModel(value); if (value === 'openai') setScope('public'); resetConversation() }
  const changeScope = (value: ChatScope) => { setScope(value); resetConversation() }
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight
  }, [messages, loading])
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!question.trim() || submitting.current) return
    submitting.current = true
    const controller = new AbortController()
    request.current = controller
    const value = question.trim()
    setQuestion('')
    setMessages(items => [...items, { role: 'user', text: value }])
    setLoading(true)
    try {
      const result = await askChat(value, model, scope, controller.signal)
      if (controller.signal.aborted) return
      setMessages(items => [...items, { role: 'assistant', text: result.answer, sources: result.sources, coverage: result.coverage }])
    } catch (error) {
      if (axios.isCancel(error) || controller.signal.aborted) return
      const detail = errorMessage(error, 'Không thể tạo câu trả lời. Hãy kiểm tra dịch vụ mô hình.')
      setMessages(items => [...items, { role: 'assistant', text: detail }])
    } finally { submitting.current = false; if (!controller.signal.aborted) setLoading(false); if (request.current === controller) request.current = null }
  }
  const options = models || [
    { id: 'qwen2.5:7b' as const, label: 'Qwen 2.5 · 7B (local)', configured: true },
    { id: 'llama3.1:70b' as const, label: 'Llama 3.1 · 70B (local)', configured: true },
    { id: 'openai' as const, label: 'OpenAI', configured: false },
  ]
  return <div className="grid items-start gap-5 xl:h-[calc(100dvh-4rem)] xl:grid-cols-[220px_minmax(0,1fr)_280px]">
    <aside className="card max-h-48 overflow-auto p-4 xl:max-h-full"><h2 className="mb-3 flex items-center gap-2 font-semibold"><FileText size={17} />Tài liệu ({documentPage?.total || 0})</h2>
      {scope === 'all' && <select aria-label="Kho hiển thị danh sách" className="input mb-3" value={catalogueScope} onChange={event => { setCatalogueScope(event.target.value as Scope); setDocumentOffset(0) }}><option value="private">Nội bộ</option><option value="public">Public</option></select>}
      {documentsPending ? <p role="status" className="text-sm text-slate-500">Đang tải danh sách...</p> : documentsError ? <div role="alert" className="text-sm text-red-600">Không tải được danh sách. <button className="underline" onClick={() => void retryDocuments()}>Thử lại</button></div> : docs.length ? docs.map(doc => <a href={`/documents/${encodeURIComponent(doc.id)}?scope=${visibleScope}`} target="_blank" rel="noopener noreferrer" key={doc.id} className="mb-2 block truncate rounded-lg bg-slate-50 p-2 text-xs text-slate-600 hover:text-blue-700" title={doc.filename}>{doc.filename}</a>) : <p className="text-sm text-slate-500">Chưa có tài liệu trong kho này.</p>}
      {(documentPage?.total || 0) > 50 && <div className="mt-3 flex justify-between text-xs"><button disabled={documentOffset === 0} onClick={() => setDocumentOffset(value => Math.max(0, value - 50))} className="text-blue-700 disabled:text-slate-400">Trước</button><button disabled={documentOffset + 50 >= (documentPage?.total || 0)} onClick={() => setDocumentOffset(value => value + 50)} className="text-blue-700 disabled:text-slate-400">Tiếp</button></div>}
    </aside>
    <section className="card flex h-[calc(100dvh-14rem)] min-h-[320px] min-w-0 flex-col overflow-hidden md:h-[calc(100dvh-4rem)] xl:h-full xl:min-h-0">
      <header className="shrink-0 border-b p-5"><h1 className="text-xl font-bold">Hỏi đáp với tài liệu</h1>
        <div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-xs font-medium text-slate-600">Mô hình trả lời<select className="input mt-1" value={model} disabled={loading} onChange={event => changeModel(event.target.value as ChatModel)}>{options.map(option => <option key={option.id} value={option.id} disabled={!option.configured}>{option.label}{!option.configured && ' · chưa cấu hình key'}</option>)}</select></label>
          <label className="text-xs font-medium text-slate-600">Nguồn tài liệu<select className="input mt-1" value={scope} disabled={loading || model === 'openai'} onChange={event => changeScope(event.target.value as ChatScope)}><option value="private">Nội bộ</option><option value="public">Public</option><option value="all">Nội bộ và public</option></select></label></div>
        {modelsError && <p role="alert" className="mt-2 text-xs text-amber-700">Chưa tải được trạng thái mô hình. OpenAI chưa sẵn sàng trên giao diện.</p>}
        <p className="mt-2 text-xs text-slate-500">{model === 'openai' ? 'Câu hỏi và các đoạn public liên quan sẽ được gửi tới OpenAI. Tài liệu nội bộ không được sử dụng.' : 'Mô hình local trả lời bằng tài liệu trong kho đã chọn.'}</p>
      </header>
      <div data-testid="chat-scroll" ref={scroller} className="min-h-0 flex-1 space-y-5 overflow-auto overscroll-contain p-5">
        {messages.length === 0 && <div className="py-16 text-center text-slate-400"><Search className="mx-auto mb-3" /><p>Nhập câu hỏi để bắt đầu.</p></div>}
        {messages.map((item, index) => <div key={index} className={item.role === 'user' ? 'ml-auto max-w-[80%] break-words rounded-2xl rounded-br-sm bg-blue-600 p-4 text-white' : 'max-w-[90%] break-words rounded-2xl rounded-bl-sm bg-slate-100 p-4'}>
          {item.role === 'assistant' ? <>
            {item.coverage?.completeness_unverified && <p role="status" className="mb-3 rounded-lg bg-amber-50 p-2 text-xs text-amber-800">Phạm vi truy xuất chưa đủ để xác nhận danh sách đầy đủ. Kết quả có thể còn thiếu; hãy hỏi theo từng mục/phụ lục.</p>}
            <article className="prose prose-sm max-w-none overflow-x-auto"><ReactMarkdown remarkPlugins={[hideCitationMarkers]} components={{ img: ({ alt }) => <span className="text-slate-500">{alt || 'Hình minh họa'}</span>, a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a> }}>{item.text}</ReactMarkdown></article>
            {!!item.sources?.length && <div className="mt-3 space-y-2 border-t border-slate-200 pt-3 text-xs"><p className="font-semibold text-slate-500">Mở nguồn tham chiếu</p>{item.sources.map(source => <div key={`${source.scope}:${source.document_id}:${source.chunk_index}`}><SourceLink source={source} /></div>)}</div>}
          </> : item.text}
        </div>)}
        {loading && <div className="flex items-center gap-2 text-sm text-slate-400"><span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />Đang tìm kiếm và đối chiếu bằng chứng...</div>}
      </div>
      <form onSubmit={submit} className="flex shrink-0 gap-2 border-t p-4"><input className="input min-w-0" value={question} maxLength={12000} onChange={event => setQuestion(event.target.value)} placeholder="Đặt câu hỏi về tài liệu..." /><button disabled={loading || !question.trim()} className="btn shrink-0 px-3" aria-label="Gửi"><Send size={18} /></button></form>
    </section>
    <aside className="card max-h-96 overflow-auto p-4 xl:max-h-full"><h2 className="mb-3 font-semibold">Nguồn truy xuất</h2>{latest.length ? latest.map(source => <div className="mb-3 rounded-xl border border-slate-100 p-3" key={`${source.scope}:${source.document_id}:${source.chunk_index}`}><p className="mb-2 break-words text-xs font-semibold text-blue-700"><SourceLink source={source} /></p><p className="line-clamp-6 text-xs leading-5 text-slate-500">{source.content}</p></div>) : <p className="text-sm text-slate-500">Nguồn của câu trả lời gần nhất sẽ hiện tại đây.</p>}</aside>
  </div>
}
