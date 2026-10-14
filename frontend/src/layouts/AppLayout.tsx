import { Suspense } from 'react'
import { FileText, LayoutDashboard, MessageSquare, Upload, FolderOpen, Sparkles } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useUploadQueue } from '../services/UploadProvider'
import PageBoundary from '../PageBoundary'
const links = [{to:'/',label:'Tổng quan',icon:LayoutDashboard},{to:'/upload',label:'Tải tài liệu',icon:Upload},{to:'/chat',label:'Hỏi đáp',icon:MessageSquare},{to:'/report',label:'Tạo báo cáo',icon:FileText},{to:'/documents',label:'Tài liệu',icon:FolderOpen}]
export default function AppLayout() {
  const location = useLocation()
  const { busy, progress } = useUploadQueue()
  return <div className="min-h-screen md:flex"><aside className="w-full border-b border-slate-200 bg-white p-4 md:min-h-screen md:w-64 md:border-b-0 md:border-r"><div className="mb-8 flex items-center gap-2 px-3 text-lg font-bold text-blue-700"><span className="rounded-lg bg-blue-600 p-1.5 text-white"><Sparkles size={18}/></span>DocuMind</div><nav className="flex gap-1 overflow-auto md:block">{links.map(({to,label,icon:Icon})=><NavLink end={to === '/'} key={to} to={to} className={({isActive})=>`mb-1 flex items-center gap-3 whitespace-nowrap rounded-xl px-3 py-2.5 text-sm ${isActive?'bg-blue-50 font-semibold text-blue-700':'text-slate-600 hover:bg-slate-50'}`}><Icon size={18}/>{label}</NavLink>)}</nav></aside><main className="min-w-0 flex-1 p-5 md:p-8">
    {busy && location.pathname !== '/upload' && <Link to="/upload" role="status" className="mb-4 block rounded-xl bg-blue-50 p-3 text-sm text-blue-700">Đang tải và xử lý tài liệu ({progress}%). Bấm để theo dõi.</Link>}
    <PageBoundary resetKey={location.key}><Suspense fallback={<p role="status" className="text-slate-500">Đang mở trang...</p>}><Outlet /></Suspense></PageBoundary>
  </main></div>
}
