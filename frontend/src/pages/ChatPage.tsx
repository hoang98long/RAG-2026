import { FormEvent, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import axios from 'axios'
import { chatErrorMessage } from '../utils/errors'
import { Send, FileText, Search, ExternalLink, MessageSquare, RotateCcw, Paperclip, X } from 'lucide-react'
import { askChat, askDirectChat, getDocumentPage, getChatModels } from '../services/api'
import { hideCitationMarkers, sourceUrl } from '../utils/sources'
import { showModelSelector } from '../config'
import { useAccess } from '../services/AuthProvider'
import { buildDirectConversation, directPdfError } from '../utils/directChat'
import { allowedAnswerLink, allowedDirectLink } from '../utils/answerLinks'
import type { Source, ChatModel, ChatMode, DirectChatMessage, ChatScope, Scope, Coverage } from '../types'

type Message = { role: 'user' | 'assistant'; text: string; sources?: Source[]; coverage?: Coverage; attachment?: string }

function SourceLink({ source }: { source: Source }) {
  const url = sourceUrl(source)
  const label = <>{source.document}{source.scope === 'public' && ' · Công khai'}{source.page != null && ` · Trang ${source.page}`}{source.chunk_index != null && ` · Đoạn ${source.chunk_index + 1}`}</>
  return url ? <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-start gap-1 text-blue-700 underline decoration-blue-200 underline-offset-2 hover:decoration-blue-700"><span className="min-w-0 break-all">{label}</span><ExternalLink size={12} className="mt-0.5 shrink-0" /></a> : <span>{label}</span>
}

export default function ChatPage() {
  const { privateAccess } = useAccess()
  const [mode, setMode] = useState<ChatMode>('rag')
  const [directHistory, setDirectHistory] = useState<DirectChatMessage[]>([])
  const [pdf, setPdf] = useState<File | null>(null)
  const [pdfError, setPdfError] = useState('')
  const pdfInput = useRef<HTMLInputElement>(null)
  const [historyTrimmed, setHistoryTrimmed] = useState(false)
  const [model, setModel] = useState<ChatModel>('qwen2.5:7b')
  const [scope, setScope] = useState<ChatScope>(privateAccess ? 'private' : 'public')
  const activeScope: ChatScope = !privateAccess || model === 'openai' ? 'public' : scope
  const [catalogueScope, setCatalogueScope] = useState<Scope>(privateAccess ? 'private' : 'public')
  const [documentOffset, setDocumentOffset] = useState(0)
  const visibleScope = activeScope === 'all' ? catalogueScope : activeScope
  const { data: models, isError: modelsError, isPending: modelsPending, isFetching: checkingModels, refetch: retryModels } = useQuery({ queryKey: ['chat-models', mode], queryFn: ({ signal }) => getChatModels(signal, mode), refetchInterval: 30000 })
  const { data: documentPage, isPending: documentsPending, isError: documentsError, refetch: retryDocuments } = useQuery({ queryKey: ['documents', 'paged', visibleScope, documentOffset, 50], queryFn: ({ signal }) => getDocumentPage(documentOffset, 50, visibleScope, signal), enabled: mode === 'rag' })
  const selectedModel = models?.find(option => option.id === model)
  const modelBlocked = modelsPending || modelsError || !selectedModel || selectedModel?.ready === false || selectedModel?.configured === false
  const modelsUnavailable = modelsError || (!modelsPending && (!selectedModel || selectedModel.ready === false || selectedModel.configured === false))
  const docs = documentPage?.items || []
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const submitting = useRef(false)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])
  const scroller = useRef<HTMLDivElement>(null)
  const latest = [...messages].reverse().find(message => message.role === 'assistant')?.sources || []
  const resetConversation = () => { setMessages([]); setQuestion(''); setDocumentOffset(0); setDirectHistory([]); setHistoryTrimmed(false); setPdf(null); setPdfError('') }
  const changeAttachment = (file: File | null) => {
    if (loading) return
    if (file) {
      const message = directPdfError(file)
      if (message) { setPdfError(message); return }
    }
    setPdf(file); setPdfError(''); setMessages([]); setDirectHistory([]); setHistoryTrimmed(false)
  }
  const choosePdf = (files: FileList | null) => {
    if (files?.length) {
      if (files.length !== 1) setPdfError('Chỉ chọn một PDF cho mỗi cuộc trò chuyện.')
      else changeAttachment(files[0])
    }
    if (pdfInput.current) pdfInput.current.value = ''
  }
  const changeMode = (value: ChatMode) => { if (value === mode) return; setMode(value); setModel(value === 'direct' ? 'openai' : 'qwen2.5:7b'); setScope('public'); resetConversation() }
  const changeModel = (value: ChatModel) => { setModel(value); if (value === 'openai') setScope('public'); resetConversation() }
  const changeScope = (value: ChatScope) => { setScope(value); resetConversation() }
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight
  }, [messages, loading])
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!question.trim() || submitting.current || modelBlocked) return
    submitting.current = true
    const controller = new AbortController()
    request.current = controller
    const value = question.trim()
    setQuestion('')
    setMessages(items => [...items, { role: 'user', text: value, attachment: mode === 'direct' ? pdf?.name : undefined }])
    setLoading(true)
    try {
      let result: { answer: string; sources: Source[]; coverage?: Coverage }
      if (mode === 'direct') {
        const conversation = buildDirectConversation(directHistory, value)
        result = await askDirectChat(conversation.messages, controller.signal, pdf)
        if (controller.signal.aborted) return
        setDirectHistory([...conversation.messages, { role: 'assistant', content: result.answer }])
        if (conversation.trimmed) setHistoryTrimmed(true)
      } else {
        result = await askChat(value, model, activeScope, controller.signal)
      }
      if (controller.signal.aborted) return
      setMessages(items => [...items, { role: 'assistant', text: result.answer, sources: result.sources, coverage: result.coverage }])
    } catch (error) {
      if (axios.isCancel(error) || controller.signal.aborted) return
      const detail = chatErrorMessage(error)
      setMessages(items => [...items, { role: 'assistant', text: detail }])
      setQuestion(draft => draft.trim() ? draft : value)
    } finally { submitting.current = false; if (!controller.signal.aborted) setLoading(false); if (request.current === controller) request.current = null }
  }
  const options = (models || [
    { id: 'qwen2.5:7b' as const, label: 'Qwen 2.5 · 7B (local)', configured: true },
    { id: 'llama3.1:70b' as const, label: 'Llama 3.1 · 70B (local)', configured: true },
    { id: 'openai' as const, label: 'OpenAI', configured: false },
  ]).filter(option => mode === 'rag' || option.id === 'openai')
  return <div className={`chat-grid${mode === 'direct' ? ' chat-grid-direct' : ''}`}>
    {mode === 'rag' && <aside className="card max-h-48 overflow-auto p-4 xl:max-h-full"><h2 className="mb-3 flex items-center gap-2 font-semibold"><FileText size={17} />Tài liệu ({documentPage?.total || 0})</h2>
      {activeScope === 'all' && <select aria-label="Kho hiển thị danh sách" className="input mb-3" value={catalogueScope} onChange={event => { setCatalogueScope(event.target.value as Scope); setDocumentOffset(0) }}><option value="private">Nội bộ</option><option value="public">Công khai</option></select>}
      {documentsPending ? <p role="status" className="text-sm text-slate-500">Đang tải danh sách...</p> : documentsError ? <div role="alert" className="text-sm text-red-600">Không tải được danh sách. <button className="underline" onClick={() => void retryDocuments()}>Thử lại</button></div> : docs.length ? docs.map(doc => <a href={`/documents/${encodeURIComponent(doc.id)}?scope=${visibleScope}`} target="_blank" rel="noopener noreferrer" key={doc.id} className="mb-2 block truncate rounded-lg bg-slate-50 p-2 text-xs text-slate-600 hover:text-blue-700" title={doc.filename}>{doc.filename}</a>) : <p className="text-sm text-slate-500">Chưa có tài liệu trong kho này.</p>}
      {(documentPage?.total || 0) > 50 && <div className="mt-3 flex justify-between text-xs"><button disabled={documentOffset === 0} onClick={() => setDocumentOffset(value => Math.max(0, value - 50))} className="text-blue-700 disabled:text-slate-400">Trước</button><button disabled={documentOffset + 50 >= (documentPage?.total || 0)} onClick={() => setDocumentOffset(value => value + 50)} className="text-blue-700 disabled:text-slate-400">Tiếp</button></div>}
    </aside>}
    <section className="card chat-panel">
      <header className="shrink-0 border-b border-slate-100 p-4 lg:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-xl font-bold lg:text-2xl">{mode === 'direct' ? 'Trò chuyện' : 'Hỏi đáp tài liệu'}</h1>
          <button className="btn-secondary text-xs" disabled={loading} onClick={resetConversation}><RotateCcw size={13}/>Cuộc trò chuyện mới</button>
        </div>
        <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
          <div role="group" aria-label="Chế độ hỏi đáp" className="inline-flex rounded-xl bg-slate-100 p-1">
            <button type="button" aria-pressed={mode === 'rag'} disabled={loading} onClick={() => changeMode('rag')} className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition disabled:opacity-50 ${mode === 'rag' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}><FileText size={15} aria-hidden="true"/>Hỏi tài liệu</button>
            <button type="button" aria-pressed={mode === 'direct'} disabled={loading} onClick={() => changeMode('direct')} className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition disabled:opacity-50 ${mode === 'direct' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}><MessageSquare size={15} aria-hidden="true"/>Trò chuyện</button>
          </div>
          <div className="flex flex-wrap gap-3">
            {showModelSelector && <label className="text-xs font-medium text-slate-600">Mô hình trả lời<select className="input mt-1 sm:w-48" value={model} disabled={loading || mode === 'direct'} onChange={event => changeModel(event.target.value as ChatModel)}>{options.map(option => <option key={option.id} value={option.id} disabled={!option.configured}>{option.label}{!option.configured ? ' · chưa cấu hình key' : option.ready === false ? ' · chưa sẵn sàng' : ''}</option>)}</select></label>}
            {mode === 'rag' && privateAccess && <label className="text-xs font-medium text-slate-600">Nguồn tài liệu<select className="input mt-1 sm:w-44" value={activeScope} disabled={loading || model === 'openai'} onChange={event => changeScope(event.target.value as ChatScope)}><option value="private">Nội bộ</option><option value="public">Công khai</option><option value="all">Tất cả tài liệu</option></select></label>}
          </div>
        </div>
        {modelsUnavailable && <div role="alert" className="mt-3 rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-800">Tạm thời chưa thể trả lời. Vui lòng thử lại sau.<button className="ml-2 font-semibold underline disabled:opacity-50" disabled={checkingModels} onClick={() => void retryModels()}>{checkingModels ? 'Đang thử lại...' : 'Thử lại'}</button></div>}
        {historyTrimmed && <p role="status" className="mt-2 text-xs text-amber-700">Với cuộc trò chuyện dài, bạn nên nhắc lại các chi tiết quan trọng.</p>}
      </header>
      <div data-testid="chat-scroll" ref={scroller} className="min-h-0 flex-1 space-y-5 overflow-auto overscroll-contain p-5">
        {messages.length === 0 && <div className="flex h-full min-h-48 flex-col items-center justify-center px-2 py-8 text-center"><span className="mb-5 rounded-2xl bg-indigo-50 p-4 text-indigo-500">{mode === 'direct' ? <MessageSquare size={27}/> : <Search size={27}/>}</span><h2 className="text-lg font-semibold">{mode === 'direct' ? 'Bạn muốn trao đổi điều gì?' : 'Bạn muốn tìm gì trong tài liệu?'}</h2>{mode === 'rag' && <p className="mt-2 max-w-sm text-sm leading-6 text-slate-400">Tìm thông tin và xem nguồn trong tài liệu của bạn.</p>}</div>}
        {messages.map((item, index) => <div key={index} className={item.role === 'user' ? 'ml-auto max-w-[88%] break-words rounded-2xl rounded-br-md bg-indigo-600 p-4 text-sm leading-6 text-white shadow-sm' : 'max-w-full break-words rounded-2xl rounded-bl-md border border-slate-100 bg-slate-50/80 p-4'}>
          {item.role === 'assistant' ? <>
            {item.coverage?.completeness_unverified && <p role="status" className="mb-3 rounded-lg bg-amber-50 p-2 text-xs text-amber-800">Câu trả lời có thể chưa đầy đủ. Bạn có thể hỏi cụ thể hơn và kiểm tra các nguồn bên dưới.</p>}
            <article className="prose prose-sm max-w-none overflow-x-auto"><ReactMarkdown remarkPlugins={mode === 'direct' ? [] : [hideCitationMarkers]} components={{ img: ({ alt }) => <span className="text-slate-500">{alt || 'Hình minh họa'}</span>, a: ({ children, href }) => { const safe = mode === 'direct' ? allowedDirectLink(href, window.location.origin) : allowedAnswerLink(href, item.sources || [], window.location.origin); return safe ? <a href={safe} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span> } }}>{item.text}</ReactMarkdown></article>
            {!!item.sources?.length && <div className="mt-3 space-y-2 border-t border-slate-200 pt-3 text-xs"><p className="font-semibold text-slate-500">Mở nguồn tham chiếu</p>{item.sources.map(source => <div key={`${source.scope}:${source.document_id}:${source.chunk_index}`}><SourceLink source={source} /></div>)}</div>}
          </> : <>{item.attachment && <p className="mb-2 flex items-center gap-2 text-xs text-indigo-100"><FileText size={14} className="shrink-0"/><span className="break-all">{item.attachment}</span></p>}{item.text}</>}
        </div>)}
        {loading && <div className="flex items-center gap-2 text-sm text-slate-400"><span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />{mode === 'direct' ? 'Đang trả lời...' : 'Đang tìm câu trả lời...'}</div>}
      </div>
      <form onSubmit={submit} className="shrink-0 border-t border-slate-100 bg-white p-4">
        {mode === 'direct' && pdf && <div className="mb-3 flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
          <FileText size={17} className="shrink-0 text-indigo-600" aria-hidden="true"/><span className="min-w-0 flex-1 truncate" title={pdf.name}>{pdf.name}</span>
          <button type="button" aria-label="Gỡ tệp" title="Gỡ tệp và bắt đầu cuộc trò chuyện mới" disabled={loading} onClick={() => changeAttachment(null)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 disabled:opacity-50"><X size={16}/></button>
        </div>}
        {pdfError && <p role="alert" className="mb-2 text-xs text-red-600">{pdfError}</p>}
        <div className="flex gap-2">
          {mode === 'direct' && <><input ref={pdfInput} aria-label="Chọn tệp PDF" type="file" accept=".pdf,application/pdf" className="hidden" disabled={loading} onChange={event => choosePdf(event.target.files)}/><button type="button" className="btn-secondary shrink-0 px-2.5" aria-label="Đính kèm PDF" title="Đính kèm một PDF, tối đa 10 MB và 100 trang" disabled={loading} onClick={() => pdfInput.current?.click()}><Paperclip size={18}/></button></>}
          <input className="input min-w-0" value={question} maxLength={12000} onChange={event => setQuestion(event.target.value)} placeholder={mode === 'direct' ? 'Nhập tin nhắn...' : 'Đặt câu hỏi về tài liệu...'} /><button disabled={loading || !question.trim() || modelBlocked} className="btn shrink-0 px-3" aria-label="Gửi"><Send size={18}/></button>
        </div>
      </form>
    </section>
    {mode === 'rag' && <aside className="card max-h-96 overflow-auto p-4 xl:max-h-full"><h2 className="mb-3 font-semibold">Nguồn tham khảo</h2>{latest.length ? latest.map(source => <div className="mb-3 rounded-xl border border-slate-100 p-3" key={`${source.scope}:${source.document_id}:${source.chunk_index}`}><p className="mb-2 break-words text-xs font-semibold text-blue-700"><SourceLink source={source} /></p><p className="line-clamp-6 text-xs leading-5 text-slate-500">{source.content}</p></div>) : <p className="text-sm text-slate-500">Nguồn của câu trả lời gần nhất sẽ hiện tại đây.</p>}</aside>}
  </div>
}
