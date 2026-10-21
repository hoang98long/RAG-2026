import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './services/AuthProvider'
import { UploadProvider } from './services/UploadProvider'
import { retryRead } from './utils/errors'
import App from './App'
import './index.css'
const query = new QueryClient({ defaultOptions: { queries: { retry: retryRead, staleTime: 30000 }, mutations: { retry: false } } })
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={query}><AuthProvider><UploadProvider><BrowserRouter><App /></BrowserRouter></UploadProvider></AuthProvider></QueryClientProvider></React.StrictMode>)
