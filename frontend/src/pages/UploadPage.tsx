import { useAccess } from '../services/AuthProvider'
import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { UploadCloud, FileCheck, X } from 'lucide-react'
import type { Scope } from '../types'
import { getUploadLimits } from '../services/api'
import { useUploadQueue } from '../services/UploadProvider'

export default function UploadPage() {
  const { privateAccess } = useAccess()
  const input = useRef<HTMLInputElement>(null)
  const { scope, files, progress, busy, message, failed, add, changeScope, remove, submit } = useUploadQueue()
  const { data: limits } = useQuery({ queryKey: ['upload-limits'], queryFn: ({ signal }) => getUploadLimits(signal) })
  const selectFiles = (list: FileList | null) => { add(list); if (input.current) input.current.value = '' }
  if (!privateAccess) return <div className="card mx-auto max-w-xl p-8 text-center"><h1 className="text-xl font-bold">Cần quyền nội bộ</h1><p className="mt-3 text-sm leading-6 text-slate-500">Đăng nhập nội bộ ở góc trên để quản lý tài liệu và tạo báo cáo.</p></div>
  return <div className="mx-auto max-w-5xl">
    <p className="page-eyebrow">THƯ VIỆN TÀI LIỆU</p><h1 className="text-3xl font-bold">Tải tài liệu</h1>
    <p className="mt-2 text-slate-500">Chọn nhiều PDF/DOCX; các tệp được xử lý lần lượt.{limits && ` Tối đa ${limits.max_file_mb} MiB mỗi tệp.`} PDF scan cần được OCR trước.</p>
    <label className="mt-5 block max-w-sm text-sm font-medium">Kho tài liệu<select className="input mt-1" value={scope} disabled={busy} onChange={event => changeScope(event.target.value as Scope)}><option value="private">Nội bộ · chỉ mô hình local</option><option value="public">Public · cho phép sử dụng với OpenAI</option></select></label>
    <p className="mt-2 text-sm text-slate-500">{scope === 'public' ? 'Chỉ tải tài liệu được phép chia sẻ. Nội dung public có thể được gửi tới OpenAI khi bạn chọn mô hình này.' : 'Tài liệu nội bộ được lưu riêng và chỉ dùng với mô hình local.'}</p>
    <div onDrop={event => { event.preventDefault(); selectFiles(event.dataTransfer.files) }} onDragOver={event => event.preventDefault()} onClick={() => !busy && input.current?.click()} className="card mt-7 cursor-pointer border-2 border-dashed border-blue-200 p-10 text-center transition hover:border-indigo-400 hover:bg-indigo-50/30 sm:p-14">
      <UploadCloud className="mx-auto text-blue-600" size={38} /><p className="mt-4 font-semibold">Kéo thả tài liệu vào đây</p><p className="mt-1 text-sm text-slate-500">hoặc bấm để chọn tệp · PDF, DOCX</p>
      <input ref={input} onChange={event => selectFiles(event.target.files)} disabled={busy} className="hidden" type="file" multiple accept=".pdf,.docx" />
    </div>
    {files.length > 0 && <div className="card mt-5 p-5">
      <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">Tệp chờ tải ({files.length})</h2><button disabled={busy} className="text-sm text-slate-500" onClick={() => remove()}>Xóa tất cả</button></div>
      {files.map((file, index) => <div className="flex items-center justify-between border-t py-3 text-sm" key={file.name + index}><span className="flex min-w-0 items-center gap-2"><FileCheck size={17} className="shrink-0 text-blue-600" /><span className="break-all">{file.name}</span></span><button disabled={busy} aria-label={`Bỏ ${file.name}`} onClick={() => remove(file)}><X size={17} /></button></div>)}
      {busy && <div className="mt-3"><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-blue-600 transition-all" style={{ width: `${progress}%` }} /></div><p className="mt-2 text-sm text-slate-500">{progress === 100 ? 'Đã gửi tệp, đang chờ lập chỉ mục hoàn tất...' : 'Đang gửi tệp và lập chỉ mục lần lượt...'}</p></div>}
      <button disabled={busy} onClick={() => void submit(limits?.max_file_mb)} className="btn mt-5">{busy ? 'Đang tải và xử lý...' : 'Tải lên và xử lý'}</button>
    </div>}
    {message && <p role={failed ? 'alert' : 'status'} className={`mt-4 text-sm ${failed ? 'text-red-600' : 'text-blue-700'}`}>{message}</p>}
  </div>
}
