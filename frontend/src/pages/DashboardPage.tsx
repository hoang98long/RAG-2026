import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, MessageSquare, FolderOpen } from 'lucide-react'
import { getDashboard } from '../services/api'
import { errorMessage } from '../utils/errors'
import type { Scope } from '../types'
const cards=[{key:'documents',label:'Tài liệu',icon:FolderOpen,color:'bg-blue-100 text-blue-700'},{key:'chats',label:'Lượt hỏi đáp',icon:MessageSquare,color:'bg-violet-100 text-violet-700'},{key:'reports',label:'Báo cáo đã tạo',icon:FileText,color:'bg-cyan-100 text-cyan-700'}] as const
export default function DashboardPage() {
  const [scope, setScope] = useState<Scope>('private')
  const { data, isPending, error, refetch } = useQuery({ queryKey: ['dashboard', scope], queryFn: ({ signal }) => getDashboard(scope, signal) })
  return <><header className="mb-8"><p className="text-sm font-medium text-blue-600">KHÔNG GIAN LÀM VIỆC</p><h1 className="mt-1 text-3xl font-bold">Tổng quan tài liệu</h1><p className="mt-2 text-slate-500">Tải tài liệu, hỏi đáp và tạo báo cáo theo kho đã chọn.</p>
    <label className="mt-5 block max-w-sm text-sm font-medium">Kho thống kê<select className="input mt-1" value={scope} onChange={event => setScope(event.target.value as Scope)}><option value="private">Nội bộ</option><option value="public">Public</option></select></label></header>
    {error && <p role="alert" className="mb-4 text-sm text-red-600">{errorMessage(error, 'Không thể tải thống kê.')} <button className="underline" onClick={() => void refetch()}>Thử lại</button></p>}
    <div className="grid gap-4 sm:grid-cols-3">{cards.map(({key,label,icon:Icon,color})=><div className="card p-5" key={key}><div className={`mb-5 inline-flex rounded-xl p-3 ${color}`}><Icon size={22}/></div><p className="text-3xl font-bold">{isPending || error ? '—' : data?.[key] ?? '—'}</p><p className="mt-1 text-sm text-slate-500">{label}</p></div>)}</div>
    <div className="card mt-6 p-6"><h2 className="font-semibold">Bắt đầu nhanh</h2><p className="mt-2 text-sm leading-6 text-slate-500">Tải PDF hoặc DOCX lên, sau đó dùng trang Hỏi đáp để đặt câu hỏi về nội dung. Bạn cũng có thể tạo báo cáo có cấu trúc từ nguồn tài liệu đã tải.</p></div>
  </>
}
