import { useRef, useState } from 'react'
import axios from 'axios'
import { useQueryClient } from '@tanstack/react-query'
import { UploadCloud, FileCheck, X } from 'lucide-react'
import { uploadDocuments } from '../services/api'

function uploadError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    const message = error.response?.data?.message
    if (typeof message === 'string') return message
    if (!error.response) return 'Không kết nối được backend. Hãy kiểm tra dịch vụ và mạng rồi thử lại.'
    if (error.response.status === 413) return 'Tệp quá lớn. Hãy giảm kích thước hoặc chia nhỏ tệp rồi tải lại.'
    if (error.response.status >= 500) return 'Backend xử lý tài liệu thất bại. Hãy kiểm tra log backend và kết nối tới Ollama embedding.'
    return `Không thể tải tài liệu (HTTP ${error.response.status}). Hãy kiểm tra định dạng PDF/DOCX.`
  }
  return 'Không thể tải tài liệu. Vui lòng thử lại.'
}

export default function UploadPage() {
  const input = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [failed, setFailed] = useState(false)
  const query = useQueryClient()
  const add = (list: FileList | null) => {
    if (busy) return
    setMessage('')
    setFiles(prev => [...prev, ...Array.from(list || [])].filter((file, index, all) => all.findIndex(other => other.name === file.name && other.size === file.size) === index))
    if (input.current) input.current.value = ''
  }
  const submit = async () => {
    if (!files.length || busy) return
    setBusy(true)
    setMessage('')
    setFailed(false)
    setProgress(0)
    try {
      await uploadDocuments(files, setProgress)
      setMessage('Tải và lập chỉ mục tài liệu thành công.')
      setFiles([])
      query.invalidateQueries({ queryKey: ['documents'] })
      query.invalidateQueries({ queryKey: ['dashboard'] })
    } catch (error) {
      setFailed(true)
      setMessage(uploadError(error))
    } finally { setBusy(false) }
  }
  return <>
    <h1 className="text-3xl font-bold">Tải tài liệu</h1>
    <p className="mt-2 text-slate-500">Hỗ trợ nhiều tệp PDF và DOCX trong một lần tải. PDF scan cần được OCR trước.</p>
    <div onDrop={event => { event.preventDefault(); add(event.dataTransfer.files) }} onDragOver={event => event.preventDefault()} onClick={() => !busy && input.current?.click()} className="card mt-7 cursor-pointer border-2 border-dashed border-blue-200 p-12 text-center hover:border-blue-400">
      <UploadCloud className="mx-auto text-blue-600" size={38} /><p className="mt-4 font-semibold">Kéo thả tài liệu vào đây</p><p className="mt-1 text-sm text-slate-500">hoặc bấm để chọn tệp · PDF, DOCX</p>
      <input ref={input} onChange={event => add(event.target.files)} disabled={busy} className="hidden" type="file" multiple accept=".pdf,.docx" />
    </div>
    {files.length > 0 && <div className="card mt-5 p-5">
      <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">Tệp chờ tải ({files.length})</h2><button disabled={busy} className="text-sm text-slate-500" onClick={() => setFiles([])}>Xóa tất cả</button></div>
      {files.map((file, index) => <div className="flex items-center justify-between border-t py-3 text-sm" key={file.name + index}><span className="flex items-center gap-2"><FileCheck size={17} className="text-blue-600" />{file.name}</span><button disabled={busy} aria-label={`Bỏ ${file.name}`} onClick={() => setFiles(items => items.filter((_, i) => i !== index))}><X size={17} /></button></div>)}
      {busy && <div className="mt-3"><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-blue-600 transition-all" style={{ width: `${progress}%` }} /></div>{progress === 100 && <p className="mt-2 text-sm text-slate-500">Đã gửi tệp. Đang đọc nội dung và tạo chỉ mục...</p>}</div>}
      <button disabled={busy} onClick={submit} className="btn mt-5">{busy ? (progress === 100 ? 'Đang xử lý tài liệu...' : `Đang tải ${progress}%`) : 'Tải lên và xử lý'}</button>
    </div>}
    {message && <p role={failed ? 'alert' : 'status'} className={`mt-4 text-sm ${failed ? 'text-red-600' : 'text-blue-700'}`}>{message}</p>}
  </>
}
