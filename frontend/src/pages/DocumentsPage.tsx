import { useAccess } from '../services/AuthProvider'
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2, FileText } from 'lucide-react'
import type { Scope } from '../types'
import { deleteDocument, getDocumentPage } from '../services/api'
import { errorMessage } from '../utils/errors'
export default function DocumentsPage() {
  const { privateAccess } = useAccess()
  const [scope, setScope] = useState<Scope>(privateAccess ? 'private' : 'public')
  const [offset, setOffset] = useState(0)
  const { data, isPending, isFetching, error, refetch } = useQuery({ queryKey: ['documents', 'paged', scope, offset, 50], queryFn: ({ signal }) => getDocumentPage(offset, 50, scope, signal) })
  const [confirmation, setConfirmation] = useState<{ id: string; filename: string; scope: Scope } | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { if (confirmation && dialog.current && !dialog.current.open) dialog.current.showModal() }, [confirmation])
  const query = useQueryClient()
  const deletion = useMutation({ mutationFn: ({ id, scope }: { id: string; scope: Scope }) => deleteDocument(id, scope), onSuccess: () => {
    void query.invalidateQueries({ queryKey: ['documents'] })
    void query.invalidateQueries({ queryKey: ['dashboard'] })
    void query.invalidateQueries({ queryKey: ['document-content'] })
  } })
  useEffect(() => {
    if (data && offset > 0 && offset >= data.total) setOffset(Math.max(0, Math.ceil(data.total / 50) - 1) * 50)
  }, [data, offset])
  const remove = (id: string, filename: string) => { if (!deletion.isPending) setConfirmation({ id, filename, scope }) }
  return <><p className="page-eyebrow">THƯ VIỆN TRI THỨC</p><h1 className="text-3xl font-bold">Tài liệu</h1><p className="mt-2 text-slate-500">Quản lý các nguồn dữ liệu trong không gian làm việc.</p>
    <label className="mt-5 block max-w-sm text-sm font-medium">Kho tài liệu<select className="input mt-1" value={scope} disabled={deletion.isPending || Boolean(confirmation)} onChange={event => { setScope(event.target.value as Scope); setOffset(0); deletion.reset() }}>{privateAccess && <option value="private">Nội bộ</option>}<option value="public">Public</option></select></label>
    {deletion.isError && <p role="alert" className="mt-3 text-sm text-red-600">{errorMessage(deletion.error, 'Không thể xóa tài liệu. Vui lòng thử lại.')}</p>}
    <div className="card mt-7 overflow-auto"><table className="w-full min-w-[500px] text-left text-sm"><thead className="bg-slate-50 text-slate-500"><tr><th className="p-4 font-medium">Tên tệp</th><th className="p-4 font-medium">Thời gian tải</th><th className="p-4" /></tr></thead><tbody>
      {isPending ? <tr><td className="p-5" colSpan={3}>Đang tải...</td></tr> : error ? <tr><td className="p-5 text-red-600" colSpan={3}><span role="alert">{errorMessage(error, 'Không thể tải danh sách tài liệu.')}</span> <button className="underline" onClick={() => void refetch()}>Thử lại</button></td></tr> : data?.items.length ? data.items.map(d => <tr className="border-t" key={d.id}><td className="p-4"><a href={`/documents/${encodeURIComponent(d.id)}?scope=${scope}`} target="_blank" rel="noopener noreferrer" className="flex min-w-0 items-center gap-3 font-medium text-indigo-700"><FileText size={18} className="shrink-0" /><span className="break-all">{d.filename}</span></a></td><td className="p-4 text-slate-500">{new Date(d.upload_time).toLocaleString('vi-VN')}</td><td className="p-4 text-right">{privateAccess && <button title="Xóa" disabled={deletion.isPending || Boolean(confirmation)} onClick={() => remove(d.id, d.filename)} className="rounded-lg p-2 text-red-500 hover:bg-red-50 disabled:opacity-50"><Trash2 size={18} /></button>}</td></tr>) : <tr><td className="p-8 text-center text-slate-500" colSpan={3}>Chưa có tài liệu nào.</td></tr>}
    </tbody></table></div>
    {!!data?.total && !error && <div className="mt-4 flex items-center justify-between gap-3 text-sm"><span>{offset + 1}–{Math.min(offset + 50, data.total)} / {data.total} tài liệu</span><div className="flex gap-3"><button disabled={offset === 0 || isFetching || deletion.isPending} onClick={() => setOffset(value => Math.max(0, value - 50))} className="text-blue-700 disabled:text-slate-400">Trước</button><button disabled={offset + 50 >= data.total || isFetching || deletion.isPending} onClick={() => setOffset(value => value + 50)} className="text-blue-700 disabled:text-slate-400">Tiếp</button></div></div>}
    {confirmation && <dialog ref={dialog} onCancel={() => setConfirmation(null)} aria-labelledby="delete-title" className="max-w-sm rounded-2xl border border-slate-200 p-6 backdrop:bg-slate-900/40"><h2 id="delete-title" className="font-semibold">Xóa tài liệu này?</h2><p className="mt-3 break-all text-sm text-slate-600">{confirmation.filename}</p><div className="mt-5 flex justify-end gap-3"><button className="rounded-lg border px-4 py-2 text-sm" onClick={() => setConfirmation(null)}>Hủy</button><button className="btn bg-red-600 hover:bg-red-700" onClick={() => { deletion.mutate({ id: confirmation.id, scope: confirmation.scope }); setConfirmation(null) }}>Xóa tài liệu</button></div></dialog>}
  </>
}
