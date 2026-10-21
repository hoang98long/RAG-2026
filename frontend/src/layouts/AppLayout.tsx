import { Suspense, useLayoutEffect, useRef } from 'react'
import { FileText, LayoutDashboard, MessageSquare, Upload, FolderOpen, BookOpen, ArrowUpRight, ChevronRight } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useUploadQueue } from '../services/UploadProvider'
import { useAccess } from '../services/AuthProvider'
import AccessControl from '../components/AccessControl'
import PageBoundary from '../PageBoundary'
const links = [{to:'/',label:'Tổng quan',icon:LayoutDashboard},{to:'/upload',label:'Tải tài liệu',icon:Upload,internal:true},{to:'/chat',label:'Hỏi đáp',icon:MessageSquare},{to:'/report',label:'Tạo báo cáo',icon:FileText,internal:true},{to:'/documents',label:'Tài liệu',icon:FolderOpen}]
export default function AppLayout() {
  const location = useLocation()
  const { busy, progress } = useUploadQueue()
  const { privateAccess } = useAccess()
  const main = useRef<HTMLElement>(null)
  const activity = useRef<HTMLAnchorElement>(null)
  const visibleLinks = links.filter(link => !link.internal || privateAccess)
  const active = links.find(link => link.to === location.pathname)?.label || 'Đọc tài liệu'
  useLayoutEffect(() => {
    const container = main.current, banner = activity.current
    const measure = () => {
      const height = banner ? banner.getBoundingClientRect().height + parseFloat(getComputedStyle(banner).marginBottom || '0') : 0
      container?.style.setProperty('--upload-banner-height', `${height}px`)
    }
    measure()
    if (!banner || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(banner)
    return () => observer.disconnect()
  }, [busy, location.pathname])
  return <div className="min-h-screen md:flex">
    <aside className="z-20 w-full bg-[#101b35] text-slate-300 md:sticky md:top-0 md:flex md:h-dvh md:w-56 md:shrink-0 md:flex-col xl:w-60">
      <Link to="/" className="flex items-center gap-3 px-5 py-5 md:px-6 md:py-7"><span className="rounded-xl bg-indigo-500 p-2 text-white shadow-lg shadow-indigo-950/40"><BookOpen size={22}/></span><span><span className="block text-lg font-bold tracking-tight text-white">DocuMind<span className="text-indigo-400">.</span></span><span className="text-[10px] tracking-[0.14em] text-slate-400">KHÔNG GIAN TRI THỨC</span></span></Link>
      <p className="mb-3 hidden px-7 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 md:block">Không gian làm việc</p>
      <nav aria-label="Điều hướng chính" className="flex gap-1 overflow-auto px-3 pb-3 md:block md:space-y-1 md:px-4">{visibleLinks.map(({to,label,icon:Icon}) => <NavLink end={to === '/'} key={to} to={to} className={({isActive})=>`flex items-center gap-3 whitespace-nowrap rounded-xl px-3 py-3 text-sm transition ${isActive?'bg-indigo-500/20 font-semibold text-indigo-100 ring-1 ring-inset ring-indigo-400/20':'text-slate-400 hover:bg-white/5 hover:text-slate-100'}`}><Icon size={18}/>{label}{location.pathname === to && <span className="ml-auto hidden h-1.5 w-1.5 rounded-full bg-indigo-400 md:block"/>}</NavLink>)}</nav>
      <div className="mx-5 mb-6 mt-auto hidden rounded-2xl border border-white/10 bg-white/[0.03] p-4 md:block"><BookOpen className="mb-3 text-indigo-300" size={20}/><p className="text-sm font-medium text-slate-200">Từ tài liệu đến câu trả lời</p><p className="mt-2 text-xs leading-5 text-slate-500">Tìm thông tin, đối chiếu bằng chứng và mở đúng đoạn nguồn.</p><Link to="/chat" className="mt-4 flex items-center justify-between text-xs font-semibold text-indigo-300">Bắt đầu hỏi đáp<ArrowUpRight size={15}/></Link></div>
    </aside>
    <div className="min-w-0 flex-1">
      <header className="flex h-[72px] items-center justify-between gap-3 border-b border-slate-200/70 bg-white/90 px-4 md:px-7"><div className="flex min-w-0 items-center gap-2 text-sm"><span className="hidden text-slate-400 lg:inline">Không gian tài liệu</span><ChevronRight size={14} className="hidden text-slate-300 lg:block"/><span className="truncate font-semibold text-slate-700">{active}</span></div><AccessControl busy={busy}/></header>
      <main ref={main} className="workspace mx-auto max-w-[1800px] p-4 md:p-6">
        {busy && location.pathname !== '/upload' && <Link ref={activity} to="/upload" role="status" className="mb-4 flex items-center gap-3 rounded-xl border border-indigo-100 bg-indigo-50 p-3 text-sm text-indigo-700"><span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-indigo-500"/>Đang tải và xử lý tài liệu ({progress}%). Bấm để theo dõi.</Link>}
        <PageBoundary resetKey={location.key}><Suspense fallback={<p role="status" className="text-slate-500">Đang mở trang...</p>}><Outlet /></Suspense></PageBoundary>
      </main>
    </div>
  </div>
}
