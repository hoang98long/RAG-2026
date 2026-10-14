import { lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const UploadPage = lazy(() => import('./pages/UploadPage'))
const ChatPage = lazy(() => import('./pages/ChatPage'))
const ReportPage = lazy(() => import('./pages/ReportPage'))
const DocumentsPage = lazy(() => import('./pages/DocumentsPage'))
const DocumentViewerPage = lazy(() => import('./pages/DocumentViewerPage'))
export default function App() { return <Routes><Route element={<AppLayout />}><Route path="/" element={<DashboardPage />} /><Route path="/upload" element={<UploadPage />} /><Route path="/chat" element={<ChatPage />} /><Route path="/report" element={<ReportPage />} /><Route path="/documents" element={<DocumentsPage />} /><Route path="/documents/:documentId" element={<DocumentViewerPage />} /></Route></Routes> }
