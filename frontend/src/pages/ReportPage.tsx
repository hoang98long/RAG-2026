import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import ReactMarkdown from 'react-markdown'
import { Copy, Download, Sparkles } from 'lucide-react'
import axios from 'axios'
import { errorMessage } from '../utils/errors'
import { hideCitationMarkers, sourceUrl } from '../utils/sources'
import { createReport } from '../services/api'
import type { Source } from '../types'

type Values = { template: string; title: string; instructions: string }

export default function ReportPage() {
  const { register, handleSubmit } = useForm<Values>({ defaultValues: { template: 'technical', title: '', instructions: '' } })
  const [content, setContent] = useState('')
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])
  const submit = async (values: Values) => {
    if (submitting.current) return
    submitting.current = true
    const controller = new AbortController()
    request.current = controller
    setLoading(true)
    setError('')
    try {
      const result = await createReport(values, controller.signal)
      if (controller.signal.aborted) return
      setContent(result.content)
      setSources(result.sources)
    } catch (error) {
      if (!axios.isCancel(error) && !controller.signal.aborted) setError(errorMessage(error, 'Không thể tạo báo cáo. Hãy kiểm tra dịch vụ mô hình.'))
    } finally { submitting.current = false; if (!controller.signal.aborted) setLoading(false); if (request.current === controller) request.current = null }
  }
  const sourceLabel = (source: Source, index: number) => `[${source.source_id || `S${index + 1}`}] ${source.document}${source.page != null ? ` · Trang ${source.page}` : ''}${source.chunk_index != null ? ` · Đoạn ${source.chunk_index + 1}` : ''}`
  const exportContent = content + (sources.length ? '\n\n## Nguồn tham chiếu\n\n' + sources.map((source, index) => sourceLabel(source, index)).join('\n\n') : '')
  const [copyStatus, setCopyStatus] = useState('')
  const copy = async () => {
    try { await navigator.clipboard.writeText(exportContent); setCopyStatus('Đã sao chép báo cáo.') }
    catch { setCopyStatus('Không thể sao chép. Bạn có thể tải báo cáo về.') }
  }
  const download = () => {
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([exportContent], { type: 'text/markdown' }))
    link.download = 'bao-cao.md'
    link.click()
    setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  }
  return <div className="grid gap-6 lg:grid-cols-[370px_1fr]">
    <section><h1 className="text-3xl font-bold">Tạo báo cáo</h1><p className="mt-2 text-slate-500">Tổng hợp nội dung từ các đoạn tài liệu liên quan.</p>
      <form onSubmit={handleSubmit(submit)} className="card mt-6 space-y-4 p-5">
        <label className="block text-sm font-medium">Mẫu báo cáo<select className="input mt-1" {...register('template')}><option value="technical">Báo cáo kỹ thuật</option><option value="meeting">Tóm tắt cuộc họp</option><option value="research">Tổng quan nghiên cứu</option></select></label>
        <label className="block text-sm font-medium">Tiêu đề<input className="input mt-1" required {...register('title')} placeholder="Ví dụ: Đánh giá dự án quý 3" /></label>
        <label className="block text-sm font-medium">Yêu cầu bổ sung<textarea className="input mt-1 min-h-28" {...register('instructions')} placeholder="Nêu trọng tâm hoặc đối tượng đọc..." /></label>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <button disabled={loading} className="btn w-full"><Sparkles size={17} />{loading ? 'Đang tạo...' : 'Tạo báo cáo'}</button>
      </form>
    </section>
    <section className="card min-h-[500px] p-6">
      <div className="mb-5 flex items-center justify-between border-b pb-4"><h2 className="font-semibold">Bản xem trước</h2>{content && <div className="flex gap-2"><button aria-label="Sao chép báo cáo" onClick={() => void copy()} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><Copy size={18} /></button><button aria-label="Tải báo cáo" onClick={download} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><Download size={18} /></button></div>}</div>
      {copyStatus && <p role="status" className="mb-3 text-sm text-slate-500">{copyStatus}</p>}
      {content ? <article className="prose max-w-none"><ReactMarkdown remarkPlugins={[hideCitationMarkers]} components={{ img: ({ alt }) => <span>{alt || 'Hình minh họa'}</span>, a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a> }}>{content}</ReactMarkdown></article> : <div className="py-36 text-center text-slate-400">Báo cáo của bạn sẽ xuất hiện ở đây.</div>}
      {sources.length > 0 && <div className="mt-6 border-t pt-4"><h3 className="mb-3 font-semibold">Nguồn tham chiếu</h3>{sources.map((source, index) => <details key={source.source_id || index} className="mb-2 rounded-lg border p-3"><summary className="cursor-pointer text-sm text-blue-700">{source.document}{source.page != null && ` · Trang ${source.page}`}</summary><a href={sourceUrl(source)} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-sm text-blue-700 underline">Mở nguồn tài liệu</a><p className="mt-2 whitespace-pre-wrap text-sm text-slate-600">{source.content}</p></details>)}</div>}
    </section>
  </div>
}
