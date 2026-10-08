import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2, FileText } from 'lucide-react'
import { deleteDocument, getDocumentPage } from '../services/api'
export default function DocumentsPage() {
  const [offset, setOffset] = useState(0)
  const { data, isLoading, isError } = useQuery({ queryKey: ['documents', 'paged', offset, 50], queryFn: () => getDocumentPage(offset, 50) })
  const query = useQueryClient()
  useEffect(() => {
    if (data && offset > 0 && offset >= data.total) setOffset(Math.max(0, Math.ceil(data.total / 50) - 1) * 50)
  }, [data, offset])
  const remove = async (id: string) => {
    if (!confirm('Xóa tài liệu này?')) return
    await deleteDocument(id)
    query.invalidateQueries({ queryKey: ['documents'] })
    query.invalidateQueries({ queryKey: ['dashboard'] })
  }
  return <><h1 className="text-3xl font-bold">Tài liệu</h1><p className="mt-2 text-slate-500">Quản lý các nguồn dữ liệu trong không gian làm việc.</p>
    <div className="card mt-7 overflow-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-slate-500"><tr><th className="p-4 font-medium">Tên tệp</th><th className="p-4 font-medium">Thời gian tải</th><th className="p-4" /></tr></thead><tbody>
      {isLoading ? <tr><td className="p-5" colSpan={3}>Đang tải...</td></tr> : isError ? <tr><td className="p-5 text-red-600" colSpan={3}>Không thể tải danh sách tài liệu.</td></tr> : data?.items.length ? data.items.map(d => <tr className="border-t" key={d.id}><td className="p-4"><a href={`/documents/${encodeURIComponent(d.id)}`} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 font-medium text-blue-700"><FileText size={17} />{d.filename}</a></td><td className="p-4 text-slate-500">{new Date(d.upload_time).toLocaleString('vi-VN')}</td><td className="p-4 text-right"><button title="Xóa" onClick={() => remove(d.id)} className="rounded-lg p-2 text-red-500 hover:bg-red-50"><Trash2 size={18} /></button></td></tr>) : <tr><td className="p-8 text-center text-slate-500" colSpan={3}>Chưa có tài liệu nào.</td></tr>}
    </tbody></table></div>
    {!!data?.total && <div className="mt-4 flex items-center justify-between gap-3 text-sm"><span>{offset + 1}–{Math.min(offset + 50, data.total)} / {data.total} tài liệu</span><div className="flex gap-3"><button disabled={offset === 0 || isLoading} onClick={() => setOffset(value => Math.max(0, value - 50))} className="text-blue-700 disabled:text-slate-400">Trước</button><button disabled={offset + 50 >= data.total || isLoading} onClick={() => setOffset(value => value + 50)} className="text-blue-700 disabled:text-slate-400">Tiếp</button></div></div>}
  </>
}
