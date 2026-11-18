import { useEffect, useState } from 'react'
import { USE_MOCK } from './api/client'
import { ToastProvider } from './components/Toast'
import DashboardPage from './pages/DashboardPage'
import EventsPage from './pages/EventsPage'
import LiveMonitorPage from './pages/LiveMonitorPage'
import VideoAnalysisPage from './pages/VideoAnalysisPage'

type Page = 'dashboard' | 'events' | 'live' | 'video'

const NAV: { key: Page; label: string; icon: string }[] = [
  { key: 'dashboard', label: '관제 현황', icon: '▦' },
  { key: 'live', label: '실시간 관제', icon: '◉' },
  { key: 'events', label: '이벤트 관리', icon: '☰' },
  { key: 'video', label: '영상 분석', icon: '▶' },
]

// 주소창 #events 처럼 해시로 현재 페이지를 기억 (새로고침해도 유지)
function readHash(): Page {
  const h = window.location.hash.slice(1) as Page
  return NAV.some((n) => n.key === h) ? h : 'dashboard'
}

export default function App() {
  const [page, setPage] = useState<Page>(readHash)

  useEffect(() => {
    const onHash = () => setPage(readHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (p: Page) => { window.location.hash = p }

  return (
    <ToastProvider>
      <div className="flex min-h-full flex-col md:flex-row">
        <aside className="flex shrink-0 flex-col border-b border-zinc-800 bg-zinc-950 md:sticky md:top-0 md:h-screen md:w-56 md:border-r md:border-b-0">
          <div className="flex items-center gap-2 px-5 py-5">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-amber-400 text-sm font-black text-zinc-950">◎</span>
            <div>
              <p className="text-sm font-bold tracking-tight text-zinc-100">AI-EYE</p>
              <p className="text-[11px] text-zinc-500">불법투기 관제 시스템</p>
            </div>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:pb-0">
            {NAV.map((n) => (
              <button
                key={n.key}
                onClick={() => go(n.key)}
                className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                  page === n.key ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'
                }`}
              >
                <span className="w-4 text-center text-zinc-500">{n.icon}</span>
                {n.label}
              </button>
            ))}
          </nav>
          {USE_MOCK && (
            <p className="mx-3 mt-auto mb-4 hidden rounded-md border border-sky-500/30 bg-sky-950/40 px-3 py-2 text-[11px] text-sky-300 md:block">
              목업 모드 — 백엔드 없이 가짜 데이터로 동작 중
            </p>
          )}
        </aside>

        <main className="min-w-0 flex-1 p-4 md:p-8">
          {page === 'dashboard' && <DashboardPage onNavigate={go} />}
          {page === 'events' && <EventsPage />}
          {page === 'live' && <LiveMonitorPage />}
          {page === 'video' && <VideoAnalysisPage />}
        </main>
      </div>
    </ToastProvider>
  )
}
