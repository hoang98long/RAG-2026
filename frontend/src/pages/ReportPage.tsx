import { useAccess } from '../services/AuthProvider'
import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import { Copy, Download, Sparkles, FileText, CheckCircle2 } from 'lucide-react'
import axios from 'axios'
import { showModelSelector } from '../config'
import { errorMessage } from '../utils/errors'
import { hideCitationMarkers, sourceUrl } from '../utils/sources'
import { createReport, getChatModels, getDocumentPage } from '../services/api'
import { allowedAnswerLink } from '../utils/answerLinks'
import { reportMarkdown } from '../utils/reportExport'
import type { ReportResult, ChatModel } from '../types'

type Values = { template: string; title: string; instructions: string; outline: string }
const statuses: Record<string,string> = { output_limit:'Vượt giới hạn đầu ra', verified:'Đã kiểm chứng', draft:'Chưa bật kiểm chứng', no_evidence:'Thiếu bằng chứng', verification_failed:'Chưa đạt kiểm chứng', verification_unavailable:'Chưa kiểm chứng được', budget_exceeded:'Chưa xử lý', retrieval_unavailable:'Truy xuất tạm gián đoạn', generation_unavailable:'Viết báo cáo tạm gián đoạn' }

export default function ReportPage() {
  const { privateAccess } = useAccess()
  const { register, handleSubmit, formState:{ errors } } = useForm<Values>({ defaultValues:{ template:'technical', title:'', instructions:'', outline:'' } })
  const [model, setModel] = useState<'qwen2.5:7b'|'llama3.1:70b'>('qwen2.5:7b')
  const [selectionMode, setSelectionMode] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  useEffect(() => { const timer = setTimeout(() => { setQuery(search.trim()); setOffset(0) }, 250); return () => clearTimeout(timer) }, [search])
  const { data:models, isPending:modelsPending, isError:modelsError, refetch:retryModels } = useQuery({ queryKey:['chat-models'], queryFn:({ signal }) => getChatModels(signal), enabled:privateAccess, refetchInterval:30000 })
  const chosen = models?.find(option => option.id === model)
  const modelBlocked = modelsPending || modelsError || !chosen || chosen.ready === false
  const { data:documents, isPending:documentsPending, error:documentsError, refetch:retryDocuments } = useQuery({ queryKey:['report-documents','private',offset,query], queryFn:({ signal }) => getDocumentPage(offset,50,'private',signal,query), enabled:privateAccess && selectionMode })
  const [result, setResult] = useState<ReportResult | null>(null)
  const [resultLabel, setResultLabel] = useState('')
  const [loading, setLoading] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState('')
  const [copyStatus, setCopyStatus] = useState('')
  const submitting = useRef(false)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])
  useEffect(() => { if (!loading) return; const started = Date.now(); setElapsed(0); const timer = setInterval(() => setElapsed(Math.floor((Date.now()-started)/1000)),1000); return () => clearInterval(timer) }, [loading])
  const submit = async (values: Values) => {
    if (submitting.current || modelBlocked) return
    if (selectionMode && !selected.length) { setError('Hãy chọn ít nhất một tài liệu.'); return }
    submitting.current = true
    const controller = new AbortController(); request.current = controller
    setLoading(true); setError(''); setCopyStatus('')
    const sections = values.outline.split('\n').map(item => item.trim()).filter(Boolean)
    try {
      const data = await createReport({ template:values.template, title:values.title.trim(), instructions:values.instructions,
        model, ...(selectionMode ? { document_ids:selected } : {}), ...(sections.length ? { sections } : {}) }, controller.signal)
      if (controller.signal.aborted) return
      setResult(data); setResultLabel(showModelSelector ? `${values.title.trim()} · ${model}` : values.title.trim())
    } catch (reason) {
      if (!axios.isCancel(reason) && !controller.signal.aborted) setError(errorMessage(reason,'Không thể tạo báo cáo. Hãy kiểm tra dịch vụ mô hình.'))
    } finally { submitting.current = false; if (!controller.signal.aborted) setLoading(false); if (request.current === controller) request.current = null }
  }
  const exportContent = () => reportMarkdown(result?.content || '', result?.sources || [], window.location.origin)
  const copy = async () => {
    try { await navigator.clipboard.writeText(exportContent()); setCopyStatus('Đã sao chép báo cáo.') }
    catch { setCopyStatus('Không thể sao chép. Bạn có thể tải báo cáo về.') }
  }
  const download = () => {
    try {
      const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([exportContent()],{ type:'text/markdown;charset=utf-8' })); link.download = 'bao-cao.md'; link.click()
      setTimeout(() => URL.revokeObjectURL(link.href),1000)
    } catch { setCopyStatus('Không thể xuất báo cáo. Vui lòng thử lại.') }
  }
  const toggleDocument = (id:string) => setSelected(items => items.includes(id) ? items.filter(item => item !== id) : items.length < 20 ? [...items,id] : items)
  if (!privateAccess) return <div className="card mx-auto max-w-xl p-8 text-center"><h1 className="text-xl font-bold">Cần quyền nội bộ</h1><p className="mt-3 text-sm leading-6 text-slate-500">Đăng nhập nội bộ ở góc trên để quản lý tài liệu và tạo báo cáo.</p></div>
  return <div className="grid items-start gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
    <section><p className="page-eyebrow">TỔNG HỢP CÓ ĐỐI CHIẾU</p><h1 className="text-3xl font-bold">Tạo báo cáo</h1><p className="mt-2 text-sm leading-6 text-slate-500">Lập dàn ý, tìm nguồn cho từng mục và kiểm chứng trước khi tổng hợp.</p>
      <form onSubmit={handleSubmit(submit)} className="card mt-5 p-5"><fieldset disabled={loading} className="space-y-4 disabled:opacity-70">
        <label className="block text-sm font-medium">Mẫu báo cáo<select className="input mt-1" {...register('template')}><option value="technical">Báo cáo kỹ thuật</option><option value="meeting">Tóm tắt cuộc họp</option><option value="research">Tổng quan nghiên cứu</option></select></label>
        {showModelSelector && <label className="block text-sm font-medium">Mô hình viết báo cáo<select className="input mt-1" value={model} onChange={event => setModel(event.target.value as typeof model)}>{(models || [{ id:'qwen2.5:7b' as ChatModel, label:'Qwen 2.5 · 7B', configured:true },{ id:'llama3.1:70b' as ChatModel,label:'Llama 3.1 · 70B',configured:true }]).filter(option => option.id !== 'openai').map(option => <option key={option.id} value={option.id}>{option.label}{option.ready === false ? ' · chưa sẵn sàng' : ''}</option>)}</select></label>}
        {(modelsError || chosen?.ready === false) && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-800">Tạm thời chưa thể tạo báo cáo. Vui lòng thử lại sau. <button type="button" className="underline" onClick={() => void retryModels()}>Thử lại</button></p>}
        <label className="block text-sm font-medium">Tiêu đề<input className="input mt-1" maxLength={500} {...register('title',{ required:'Nhập tiêu đề báo cáo.',validate:value => !!value.trim() || 'Nhập tiêu đề báo cáo.' })} placeholder="Ví dụ: Đánh giá điều kiện bảo hành" /></label>
        {errors.title && <p role="alert" className="text-xs text-red-600">{errors.title.message}</p>}
        <label className="block text-sm font-medium">Yêu cầu bổ sung<textarea className="input mt-1 min-h-24" maxLength={12000} {...register('instructions')} placeholder="Nêu đối tượng đọc, phạm vi, thời kỳ và điểm cần đối chiếu..." /></label>
        <label className="block text-sm font-medium">Dàn ý tùy chọn<textarea className="input mt-1 min-h-24" {...register('outline',{ validate:value => { const items=value.split('\n').map(item => item.trim()).filter(Boolean); return (items.length <= 4 && new Set(items).size===items.length && items.every(item => item.length<=120)) || 'Nhập tối đa 4 mục khác nhau, mỗi mục tối đa 120 ký tự.' } })} placeholder={'Mỗi dòng một mục, tối đa 4 mục.\nĐể trống để hệ thống lập dàn ý.'}/></label>
        {errors.outline && <p role="alert" className="text-xs text-red-600">{errors.outline.message}</p>}
        <label className="block text-sm font-medium">Phạm vi tài liệu<select className="input mt-1" value={selectionMode ? 'selected' : 'private'} onChange={event => { setSelectionMode(event.target.value==='selected'); setOffset(0) }}><option value="private">Tìm trong kho nội bộ</option><option value="selected">Chỉ các tài liệu được chọn</option></select></label>
        {selectionMode && <div className="space-y-2 rounded-xl border border-slate-200 p-3"><div className="flex items-center justify-between text-xs text-slate-500"><span>Đã chọn {selected.length}/20 tài liệu</span>{!!selected.length && <button type="button" className="text-indigo-600" onClick={() => setSelected([])}>Bỏ chọn</button>}</div><input aria-label="Tìm tài liệu báo cáo" className="input text-sm" maxLength={100} value={search} onChange={event => setSearch(event.target.value)} placeholder="Tìm theo tên tệp..."/>
          <div className="max-h-48 space-y-1 overflow-auto">{documentsPending ? <p className="text-xs text-slate-500">Đang tải tài liệu...</p> : documentsError ? <p role="alert" className="text-xs text-red-600">Không tải được tài liệu. <button type="button" className="underline" onClick={() => void retryDocuments()}>Thử lại</button></p> : documents?.items.length ? documents.items.map(doc => <label key={doc.id} className="flex cursor-pointer items-start gap-2 rounded-lg px-1 py-2 text-xs text-slate-600"><input type="checkbox" className="mt-0.5" checked={selected.includes(doc.id)} disabled={selected.length>=20 && !selected.includes(doc.id)} onChange={() => toggleDocument(doc.id)}/><span className="min-w-0 break-all">{doc.filename}</span></label>) : <p className="text-xs text-slate-500">Không có tài liệu phù hợp.</p>}</div>
          {(documents?.total || 0)>50 && <div className="flex justify-between text-xs"><button type="button" disabled={offset===0} onClick={() => setOffset(value => Math.max(0,value-50))}>Trước</button><span>{Math.floor(offset/50)+1}/{Math.ceil((documents?.total || 0)/50)}</span><button type="button" disabled={offset+50 >= (documents?.total || 0)} onClick={() => setOffset(value => value+50)}>Tiếp</button></div>}
        </div>}
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <button disabled={loading || modelBlocked || (selectionMode && !selected.length)} className="btn w-full"><Sparkles size={17}/>{loading ? 'Đang tạo...' : 'Tạo báo cáo'}</button>
      </fieldset></form>
    </section>
    <section className="card min-h-[560px] min-w-0 p-5 md:p-7">
      <div className="mb-5 flex items-center justify-between gap-3 border-b pb-4"><div><h2 className="font-semibold">Bản xem trước</h2>{resultLabel && <p className="mt-1 break-words text-xs text-slate-500">{resultLabel}</p>}</div>{result?.content && <div className="flex shrink-0 gap-2"><button aria-label="Sao chép báo cáo" onClick={() => void copy()} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><Copy size={18}/></button><button aria-label="Tải báo cáo" onClick={download} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><Download size={18}/></button></div>}</div>
      {loading && <p role="status" className="mb-4 rounded-xl bg-indigo-50 p-4 text-sm leading-6 text-indigo-700">Đang tìm bằng chứng, viết và kiểm chứng từng mục ({elapsed} giây). Quá trình có thể mất vài phút.</p>}
      {copyStatus && <p role="status" className="mb-3 text-sm text-slate-500">{copyStatus}</p>}
      {result?.coverage?.total_sections != null && <div className="mb-5 rounded-xl border border-slate-200 bg-slate-50 p-4"><p className="flex items-center gap-2 text-sm font-semibold"><CheckCircle2 size={16}/>Đã kiểm chứng {result.coverage.verified_sections}/{result.coverage.total_sections} mục · {result.coverage.evidence_documents} tài liệu có bằng chứng</p>{result.coverage.partial && <p role="alert" className="mt-2 text-xs leading-5 text-amber-800">Báo cáo còn phần thiếu hoặc chưa được kiểm chứng đầy đủ. Hãy đọc trạng thái từng mục và kiểm tra nguồn trước khi sử dụng.</p>}{!!result.coverage.unrepresented_document_ids.length && <p className="mt-2 text-xs text-amber-800">{result.coverage.unrepresented_document_ids.length} tài liệu được chọn chưa có bằng chứng được sử dụng.</p>}
        <ul className="mt-3 space-y-1.5 text-xs">{result.sections?.map((section,index) => <li key={index} className="flex flex-wrap justify-between gap-2"><span className="text-slate-600">{section.heading}</span><span className={section.status==='verified' ? 'text-emerald-700' : 'text-amber-700'}>{statuses[section.status] || 'Chưa hoàn tất'}{section.truncated && ' · nguồn chưa đủ phạm vi'}</span></li>)}</ul></div>}
      {result?.content ? <article className="report-prose max-w-none overflow-x-auto break-words"><ReactMarkdown remarkPlugins={[hideCitationMarkers]} components={{ img:({ alt }) => <span>{alt || 'Hình minh họa'}</span>, a:({ children,href }) => { const safe=allowedAnswerLink(href,result.sources,window.location.origin); return safe ? <a href={safe} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span> } }}>{result.content}</ReactMarkdown></article> : !loading && <div className="flex flex-col items-center gap-3 py-32 text-center text-slate-400"><FileText size={32} strokeWidth={1.3}/><p>Báo cáo và trạng thái kiểm chứng sẽ xuất hiện ở đây.</p></div>}
      {!!result?.sources.length && <div className="mt-6 border-t pt-4"><h3 className="mb-3 font-semibold">Nguồn tham chiếu</h3>{result.sources.map((source,index) => <details key={source.source_id || index} className="mb-2 rounded-lg border p-3"><summary className="cursor-pointer break-words text-sm text-blue-700">{source.document}{source.page != null && ` · Trang ${source.page}`}{source.chunk_index != null && ` · Đoạn ${source.chunk_index+1}`}</summary><a href={sourceUrl(source)} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-sm text-blue-700 underline">Mở nguồn tài liệu</a><p className="mt-2 whitespace-pre-wrap text-sm text-slate-600">{source.content}</p></details>)}</div>}
    </section>
  </div>
}
