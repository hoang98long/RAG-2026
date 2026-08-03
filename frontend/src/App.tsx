import { Route, Routes } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import DashboardPage from './pages/DashboardPage'
import UploadPage from './pages/UploadPage'
import ChatPage from './pages/ChatPage'
import ReportPage from './pages/ReportPage'
import DocumentsPage from './pages/DocumentsPage'
export default function App(){return <Routes><Route element={<AppLayout/>}><Route path="/" element={<DashboardPage/>}/><Route path="/upload" element={<UploadPage/>}/><Route path="/chat" element={<ChatPage/>}/><Route path="/report" element={<ReportPage/>}/><Route path="/documents" element={<DocumentsPage/>}/></Route></Routes>}
