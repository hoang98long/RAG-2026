import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { FileText, MessageSquare, FolderOpen, ArrowUpRight, Upload, Search, BookOpen } from 'lucide-react'
import { getDashboard } from '../services/api'
import { useAccess } from '../services/AuthProvider'
import { errorMessage } from '../utils/errors'
import type { Scope } from '../types'
const cards = [{key:'documents',label:'Tài liệu trong kho',icon:FolderOpen,color:'bg-indigo-50 text-indigo-600'}, {key:'chats',label:'Lượt hỏi đáp',icon:MessageSquare,color:'bg-emerald-50 text-emerald-600'}, {key:'reports',label:'Báo cáo đã tạo',icon:FileText,color:'bg-amber-50 text-amber-600'}] as const
export default function DashboardPage() {
  const { privateAccess } = useAccess()
  const [scope, setScope] = useState<Scope>(privateAccess ? 'private' : 'public')
  const { data, isPending, error, refetch } = useQuery({ queryKey: ['dashboard', scope], queryFn: ({ signal }) => getDashboard(scope, signal) })
  return <div className="mx-auto max-w-6xl">
    <header className="mb-7 flex flex-wrap items-end justify-between gap-5"><div><p className="page-eyebrow">KHÔNG GIAN LÀM VIỆC</p><h1 className="text-2xl font-bold sm:text-3xl">Tri thức của bạn, trong tầm tay.</h1><p className="mt-2 text-sm leading-6 text-slate-500">Khám phá tài liệu và tìm câu trả lời có nguồn đối chiếu.</p></div><label className="w-full text-xs font-medium text-slate-500 sm:w-48">Kho thống kê<select className="input mt-2" value={scope} onChange={event => setScope(event.target.value as Scope)}>{privateAccess && <option value="private">Nội bộ</option>}<option value="public">Public</option></select></label></header>
    {error && <p role="alert" className="mb-5 rounded-xl bg-red-50 p-4 text-sm text-red-700">{errorMessage(error, 'Không thể tải thống kê.')} <button className="font-semibold underline" onClick={() => void refetch()}>Thử lại</button></p>}
    <div className="grid gap-4 sm:grid-cols-3">{cards.map(({key,label,icon:Icon,color})=><div className="card p-5 lg:p-6" key={key}><div className="mb-5 flex items-center justify-between"><span className={`inline-flex rounded-xl p-2.5 ${color}`}><Icon size={20}/></span><span className="rounded-full bg-slate-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">{scope === 'public' ? 'Public' : 'Nội bộ'}</span></div><p className="text-3xl font-bold tracking-tight text-slate-900">{isPending || error ? '—' : data?.[key] ?? '—'}</p><p className="mt-2 text-sm text-slate-500">{label}</p></div>)}</div>
    <section className="mt-6 overflow-hidden rounded-2xl bg-[#162440] p-6 text-white md:p-8"><div className="flex items-start justify-between gap-4"><div className="max-w-xl"><span className="mb-5 inline-flex items-center gap-2 rounded-full border border-indigo-300/20 bg-indigo-400/10 px-3 py-1 text-[11px] font-medium text-indigo-200"><Search size={12}/>HỎI ĐÁP CÓ NGUỒN</span><h2 className="text-xl font-semibold text-white sm:text-2xl">Bắt đầu từ một câu hỏi.</h2><p className="mt-3 text-sm leading-6 text-slate-400">Tìm điều kiện, đối chiếu quy định hoặc khám phá một chủ đề. Mở nguồn tham chiếu để đọc nội dung trong ngữ cảnh.</p><Link to="/chat" className="mt-6 inline-flex items-center gap-3 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-slate-800 transition hover:bg-indigo-50">Mở không gian hỏi đáp<ArrowUpRight size={16}/></Link></div><div className="hidden rounded-3xl border border-white/10 bg-white/5 p-7 text-indigo-300 sm:block"><BookOpen size={64} strokeWidth={1.2}/></div></div></section>
    <div className={`mt-6 grid gap-4 ${privateAccess ? 'sm:grid-cols-2' : ''}`}>
      {privateAccess && <Link to="/upload" className="card group flex items-start gap-4 p-5 transition hover:border-indigo-200"><span className="rounded-xl bg-slate-50 p-3 text-slate-500 group-hover:bg-indigo-50 group-hover:text-indigo-600"><Upload size={21}/></span><div className="flex-1"><h2 className="text-sm font-semibold">Thêm nguồn tri thức</h2><p className="mt-1.5 text-xs leading-5 text-slate-500">Tải PDF, DOCX và chọn kho phù hợp.</p></div><ArrowUpRight className="text-slate-300 group-hover:text-indigo-500" size={17}/></Link>}
      <Link to="/documents" className="card group flex items-start gap-4 p-5 transition hover:border-indigo-200"><span className="rounded-xl bg-slate-50 p-3 text-slate-500 group-hover:bg-indigo-50 group-hover:text-indigo-600"><FolderOpen size={21}/></span><div className="flex-1"><h2 className="text-sm font-semibold">Khám phá thư viện</h2><p className="mt-1.5 text-xs leading-5 text-slate-500">Xem tài liệu và đọc nội dung nguồn.</p></div><ArrowUpRight className="text-slate-300 group-hover:text-indigo-500" size={17}/></Link>
    </div>
  </div>
}
