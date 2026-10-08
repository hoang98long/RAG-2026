import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, useSearchParams } from 'react-router-dom'
import { ExternalLink, FileText } from 'lucide-react'
import axios from 'axios'
import { documentFileUrl, getDocumentContent } from '../services/api'

export default function DocumentViewerPage() {
  const { documentId = '' } = useParams()
  const [params] = useSearchParams()
  const chunkValue = params.get('chunk')
  const pageValue = params.get('page')
  const chunkIndex = chunkValue != null && /^\d+$/.test(chunkValue) ? Number(chunkValue) : null
  const page = pageValue != null && /^[1-9]\d*$/.test(pageValue) ? Number(pageValue) : null
  const target = useRef<HTMLElement>(null)
  const { data, isPending, error } = useQuery({ queryKey: ['document-content', documentId], queryFn: () => getDocumentContent(documentId), enabled: Boolean(documentId) })
  const targetChunk = data?.chunks.find(chunk => chunk.chunk_index === chunkIndex)
    || (page != null ? data?.chunks.find(chunk => chunk.page === page) : undefined)
  useEffect(() => {
    if (!data || !target.current) return
    const frame = requestAnimationFrame(() => {
      target.current?.scrollIntoView({ block: 'center' })
      target.current?.focus({ preventScroll: true })
    })
    return () => cancelAnimationFrame(frame)
  }, [data, chunkIndex, page])
  const errorText = axios.isAxiosError(error) && typeof error.response?.data?.detail === 'string' ? error.response.data.detail : 'Không thể mở tài liệu. Hãy kiểm tra kết nối hoặc tài liệu đã bị xóa.'
  return <section className="card flex h-[calc(100dvh-14rem)] min-h-[320px] flex-col overflow-hidden md:h-[calc(100dvh-4rem)]">
    <header className="shrink-0 border-b p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="flex min-w-0 items-center gap-2 text-lg font-bold"><FileText className="shrink-0" size={20} /><span className="break-all">{data?.filename || 'Tài liệu nguồn'}</span></h1>
        {data && <a className="btn" href={documentFileUrl(documentId, targetChunk?.page || page)} target="_blank" rel="noopener noreferrer"><ExternalLink size={16} />{data.file_type === 'pdf' ? `Mở PDF gốc${targetChunk?.page ? ` · Trang ${targetChunk.page}` : ''}` : 'Tải bản DOCX gốc'}</a>}
      </div>
      <p className="mt-2 text-sm text-slate-500">Nội dung trích xuất từ tài liệu. Đoạn được dẫn nguồn được tô nổi để đối chiếu.</p>
      {data && chunkIndex != null && !data.chunks.some(chunk => chunk.chunk_index === chunkIndex) && <p role="alert" className="mt-2 text-sm text-amber-700">Đoạn nguồn không còn trong chỉ mục hiện tại. Tài liệu có thể đã được lập lại chỉ mục.</p>}
    </header>
    <div className="min-h-0 flex-1 overflow-auto p-5 md:p-8">
      {isPending && <p role="status" className="text-slate-500">Đang mở tài liệu...</p>}
      {error && <p role="alert" className="text-red-600">{errorText}</p>}
      {data?.chunks.map(chunk => <article key={chunk.chunk_index} ref={chunk.chunk_index === targetChunk?.chunk_index ? target : undefined} tabIndex={-1} className={`mb-5 scroll-mt-6 rounded-xl border p-5 outline-none ${chunk.chunk_index === targetChunk?.chunk_index ? 'border-amber-300 bg-amber-50 ring-2 ring-amber-200' : 'border-slate-100'}`}>
        <p className="mb-3 text-xs font-semibold text-slate-500">{chunk.page != null ? `Trang ${chunk.page} · ` : ''}Đoạn {chunk.chunk_index + 1}{chunk.chunk_index === targetChunk?.chunk_index && ' · Nguồn được trích dẫn'}</p>
        <p className="whitespace-pre-wrap break-words text-sm leading-7">{chunk.content}</p>
      </article>)}
    </div>
  </section>
}
