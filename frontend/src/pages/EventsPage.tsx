import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { DumpingEvent, EventStatus } from '../api/types'
import EventDetailModal from '../components/EventDetailModal'
import StatusBadge from '../components/StatusBadge'
import { formatDateTime, labelMeta, pct, timeAgo } from '../lib/format'

const TABS: { key: EventStatus | 'ALL'; label: string }[] = [
  { key: 'ALL', label: '전체' },
  { key: 'UNCHECKED', label: '미확인' },
  { key: 'CONFIRMED', label: '투기 확정' },
  { key: 'FALSE_POSITIVE', label: '오탐' },
]
const PAGE_SIZE = 12
const POLL_MS = 5000

export default function EventsPage() {
  const [tab, setTab] = useState<EventStatus | 'ALL'>('UNCHECKED')
  const [page, setPage] = useState(1)
  const [events, setEvents] = useState<DumpingEvent[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selected, setSelected] = useState<DumpingEvent | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await api.getEvents({ status: tab === 'ALL' ? undefined : tab, page, size: PAGE_SIZE })
      setEvents(res.events)
      setTotal(res.total)
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [tab, page])

  useEffect(() => {
    setLoading(true)
    load()
  }, [load])

  // 실시간 푸시(WebSocket)가 없어서 주기적으로 다시 불러옴
  useEffect(() => {
    if (!autoRefresh) return
    const t = setInterval(load, POLL_MS)
    return () => clearInterval(t)
  }, [autoRefresh, load])

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">이벤트 관리</h1>
          <p className="mt-1 text-sm text-zinc-500">AI가 확정한 투기 의심 이벤트를 검토하고 판정합니다.</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-zinc-400">
          <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} className="accent-amber-400" />
          {POLL_MS / 1000}초마다 자동 새로고침
        </label>
      </header>

      <div className="flex gap-1 border-b border-zinc-800">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); setPage(1) }}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition ${
              tab === t.key ? 'border-amber-400 text-zinc-100' : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {t.label}
          </button>
        ))}
        <span className="ml-auto self-center font-mono text-xs text-zinc-500">총 {total}건</span>
      </div>

      {error && <p className="rounded-lg border border-rose-500/30 bg-rose-950/40 px-4 py-3 text-sm text-rose-300">{error}</p>}

      {loading && events.length === 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => <div key={i} className="aspect-[4/3] animate-pulse rounded-xl bg-zinc-900" />)}
        </div>
      ) : events.length === 0 && !error ? (
        <p className="py-20 text-center text-zinc-500">해당 상태의 이벤트가 없어요.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {events.map((e) => (
            <button
              key={e.id}
              onClick={() => setSelected(e)}
              className="group overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900 text-left transition hover:border-zinc-600"
            >
              <div className="relative aspect-video overflow-hidden bg-black">
                <img src={e.snapshot_path} alt="" loading="lazy" className="h-full w-full object-cover transition group-hover:scale-[1.02]" />
                <span className="absolute top-2 left-2 rounded bg-black/70 px-1.5 py-0.5 font-mono text-[11px] text-zinc-300">{e.cctv_id}</span>
                <span className="absolute top-2 right-2"><StatusBadge status={e.status} /></span>
              </div>
              <div className="flex items-center justify-between px-3 py-2.5">
                <div>
                  <p className="text-sm font-medium text-zinc-200">{labelMeta(e.trash_type).name} <span className="font-mono text-xs text-zinc-500">{pct(e.confidence)}</span></p>
                  <p className="font-mono text-xs text-zinc-500">{formatDateTime(e.detected_at)}</p>
                </div>
                <span className="text-xs text-zinc-500">{timeAgo(e.detected_at)}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {pages > 1 && (
        <nav className="flex items-center justify-center gap-2 pt-2">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded-md px-3 py-1.5 text-sm text-zinc-400 hover:bg-zinc-800 disabled:opacity-30">이전</button>
          <span className="font-mono text-sm text-zinc-400">{page} / {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="rounded-md px-3 py-1.5 text-sm text-zinc-400 hover:bg-zinc-800 disabled:opacity-30">다음</button>
        </nav>
      )}

      {selected && (
        <EventDetailModal
          event={selected}
          onClose={() => setSelected(null)}
          onUpdated={(u) => { setSelected(u); load() }}
        />
      )}
    </div>
  )
}
