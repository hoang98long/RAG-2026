import { FormEvent, useEffect, useRef, useState } from 'react'
import { KeyRound, LogOut, ShieldCheck, X } from 'lucide-react'
import { useAccess } from '../services/AuthProvider'
import { errorMessage } from '../utils/errors'

export default function AccessControl({ busy = false }: { busy?: boolean }) {
  const { privateAccess, configured, login, logout } = useAccess()
  const dialog = useRef<HTMLDialogElement>(null)
  const [open, setOpen] = useState(false)
  const [token, setToken] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (open && dialog.current && !dialog.current.open) dialog.current.showModal() }, [open])
  const close = () => { if (!pending) { setOpen(false); setToken(''); setError('') } }
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (pending) return
    setPending(true); setError('')
    try { await login(token); setToken(''); setOpen(false) }
    catch (reason) { setError(errorMessage(reason, 'Không thể đăng nhập.')); setToken('') }
    finally { setPending(false) }
  }
  const signOut = async () => {
    setPending(true); setError('')
    try { await logout() } catch (reason) { setError(errorMessage(reason, 'Không thể đăng xuất.')) }
    finally { setPending(false) }
  }
  return <div className="flex items-center gap-3">
    <span className={`hidden items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold sm:inline-flex ${privateAccess ? 'bg-emerald-50 text-emerald-700' : 'bg-sky-50 text-sky-700'}`}><ShieldCheck size={14}/>{privateAccess ? 'Quyền nội bộ' : 'Truy cập public'}</span>
    <button className="btn-secondary whitespace-nowrap text-xs" disabled={pending || busy} onClick={() => privateAccess ? void signOut() : setOpen(true)}>{privateAccess ? <><LogOut size={14}/>Đăng xuất</> : <><KeyRound size={14}/>Đăng nhập nội bộ</>}</button>
    {error && !open && <span role="alert" className="max-w-48 text-xs text-red-600">{error}</span>}
    {open && <dialog ref={dialog} aria-labelledby="access-title" onCancel={event => { if (pending) event.preventDefault(); else close() }} className="w-[calc(100%-2rem)] max-w-md rounded-3xl border border-slate-200 p-7 shadow-2xl backdrop:bg-slate-950/50">
      <div className="mb-5 flex items-center justify-between"><div className="rounded-2xl bg-indigo-50 p-3 text-indigo-600"><KeyRound size={23}/></div><button aria-label="Đóng đăng nhập" disabled={pending} onClick={close} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"><X size={19}/></button></div>
      <h2 id="access-title" className="text-xl font-bold text-slate-900">Không gian nội bộ</h2><p className="mt-2 text-sm leading-6 text-slate-500">Nhập khóa do quản trị viên cung cấp để sử dụng tài liệu nội bộ và quản lý tài liệu.</p>
      {!configured && <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">Máy chủ chưa cấu hình khóa truy cập nội bộ.</p>}
      <form onSubmit={event => void submit(event)} className="mt-5 space-y-4"><label className="block text-sm font-medium text-slate-700">Khóa truy cập<input autoFocus autoComplete="off" type="password" className="input mt-2" value={token} onChange={event => setToken(event.target.value)} required maxLength={512} disabled={pending}/></label>{error && <p role="alert" className="text-sm text-red-600">{error}</p>}<button className="btn w-full" disabled={pending || !configured}>{pending ? 'Đang xác thực...' : 'Mở không gian nội bộ'}</button></form>
    </dialog>}
  </div>
}
