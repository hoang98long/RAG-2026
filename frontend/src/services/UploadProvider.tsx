import { createContext, useContext, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { uploadDocuments } from '../services/api'
import { uploadRequestId } from '../utils/uploadId'
import { errorMessage } from '../utils/errors'
import type { Scope } from '../types'

function useQueueState() {
  const [scope, setScope] = useState<Scope>('private')
  const [files, setFiles] = useState<File[]>([])
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [failed, setFailed] = useState(false)
  const locked = useRef(false)
  const ids = useRef(new WeakMap<File, string>())
  const query = useQueryClient()
  const add = (list: FileList | null) => {
    if (locked.current) return
    const picked = Array.from(list || [])
    const invalid = picked.find(file => !/\.(pdf|docx)$/i.test(file.name))
    setFailed(Boolean(invalid))
    setMessage(invalid ? `${invalid.name}: chỉ hỗ trợ PDF hoặc DOCX.` : '')
    setFiles(previous => [...previous, ...picked.filter(file => /\.(pdf|docx)$/i.test(file.name))].filter((file, index, all) =>
      all.findIndex(other => other.name === file.name && other.size === file.size && other.lastModified === file.lastModified) === index))
  }
  const changeScope = (value: Scope) => {
    if (locked.current) return
    setScope(value); setFiles([]); setMessage(''); setFailed(false); setProgress(0)
  }
  const remove = (file?: File) => { if (!locked.current) setFiles(previous => file ? previous.filter(item => item !== file) : []) }
  const submit = async (maxFileMb?: number) => {
    if (locked.current || !files.length) return
    const oversized = maxFileMb && files.find(file => file.size > maxFileMb * 1024 * 1024)
    if (oversized) { setFailed(true); setMessage(`${oversized.name}: vượt giới hạn ${maxFileMb} MiB mỗi tệp.`); return }
    locked.current = true
    setBusy(true); setProgress(0); setMessage(''); setFailed(false)
    let uploaded = 0
    const selectedFiles = [...files]
    try {
      await uploadDocuments(selectedFiles, setProgress, file => {
        uploaded++
        setFiles(previous => previous.filter(item => item !== file))
        void query.invalidateQueries({ queryKey: ['documents'] })
        void query.invalidateQueries({ queryKey: ['dashboard'] })
      }, scope, file => {
        let id = ids.current.get(file)
        if (!id) { id = uploadRequestId(); ids.current.set(file, id) }
        return id
      })
      setMessage(`Đã tải và lập chỉ mục thành công ${uploaded} tài liệu.`)
    } catch (error) {
      setFailed(true)
      setMessage(`${uploaded ? `Đã lưu ${uploaded} tài liệu. ` : ''}${errorMessage(error, 'Không thể xử lý tài liệu. Hãy kiểm tra dịch vụ embedding.')} Các tệp chưa hoàn tất vẫn ở danh sách chờ.`)
    } finally { locked.current = false; setBusy(false) }
  }
  return { scope, files, progress, busy, message, failed, add, changeScope, remove, submit }
}
const UploadContext = createContext<ReturnType<typeof useQueueState> | null>(null)
export function UploadProvider({ children }: { children: ReactNode }) {
  const state = useQueueState()
  return <UploadContext.Provider value={state}>{children}</UploadContext.Provider>
}
export function useUploadQueue() {
  const state = useContext(UploadContext)
  if (!state) throw new Error('UploadProvider is missing')
  return state
}
