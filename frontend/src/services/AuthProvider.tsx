import { createContext, Fragment, useContext, useEffect, useRef, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getAccessSession, loginPrivate, logoutPrivate } from './api'

type Access = { privateAccess: boolean; configured: boolean; login: (token: string) => Promise<void>; logout: () => Promise<void> }
const Context = createContext<Access | null>(null)
export function AuthProvider({ children }: { children: ReactNode }) {
  const query = useQueryClient()
  const { data, isPending, isError, isFetching, refetch } = useQuery({ queryKey: ['access-session'], queryFn: ({ signal }) => getAccessSession(signal), staleTime: 15000, retry: false })
  const privateAccess = !isError && data?.private_access === true
  const previous = useRef(privateAccess)
  const accessChannel = useRef<BroadcastChannel | null>(null)
  const clearWorkspace = async () => {
    await query.cancelQueries({ predicate: entry => entry.queryKey[0] !== 'access-session' })
    query.removeQueries({ predicate: entry => entry.queryKey[0] !== 'access-session' })
  }
  useEffect(() => {
    if (previous.current && !privateAccess) {
      void query.cancelQueries({ predicate: entry => entry.queryKey.includes('private') })
      query.removeQueries({ predicate: entry => entry.queryKey.includes('private') })
    }
    previous.current = privateAccess
  }, [privateAccess])
  useEffect(() => {
    const refresh = () => { void query.invalidateQueries({ queryKey: ['access-session'] }) }
    window.addEventListener('documind-access-expired', refresh)
    const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('documind-access')
    accessChannel.current = channel
    if (channel) channel.onmessage = event => {
      if (event.data === 'logout') {
        void clearWorkspace().then(() => query.setQueryData(['access-session'], { private_access: false, private_configured: true }))
      } else if (event.data === 'login') refresh()
    }
    return () => { window.removeEventListener('documind-access-expired', refresh); channel?.close(); accessChannel.current = null }
  }, [query])
  const broadcast = (event: string) => {
    accessChannel.current?.postMessage(event)
  }
  const login = async (token: string) => {
    await loginPrivate(token)
    await clearWorkspace()
    query.setQueryData(['access-session'], { private_access: true, private_configured: true })
    broadcast('login')
  }
  const logout = async () => {
    await logoutPrivate()
    await clearWorkspace()
    query.setQueryData(['access-session'], { private_access: false, private_configured: data?.private_configured ?? false })
    broadcast('logout')
  }
  if (isPending) return <div className="flex min-h-screen items-center justify-center text-sm text-slate-500" role="status">Đang mở không gian tài liệu...</div>
  if (isError) return <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6"><div className="card w-full max-w-md p-7 text-center"><h1 className="text-xl font-semibold text-slate-900">Chưa kết nối được máy chủ</h1><p role="alert" className="mt-3 text-sm leading-6 text-slate-500">Không thể kiểm tra phiên truy cập. Vui lòng kiểm tra kết nối và thử lại để tiếp tục.</p><button className="btn mt-5" disabled={isFetching} onClick={() => void refetch()}>{isFetching ? 'Đang kết nối...' : 'Kết nối lại'}</button></div></div>
  return <Context.Provider value={{ privateAccess, configured: data?.private_configured === true, login, logout }}><Fragment key={privateAccess ? 'internal' : 'public'}>{children}</Fragment></Context.Provider>
}
export function useAccess() { const value = useContext(Context); if (!value) throw new Error('Missing access context'); return value }
