import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { DumpingEvent, EventStatus } from '../api/types'
import EventDetailModal from '../components/EventDetailModal'
import StatusBadge from '../components/StatusBadge'
import { labelMeta, parseServerDate, timeAgo } from '../lib/format'

type Counts = Record<'ALL' | EventStatus, number>

interface Props { onNavigate: (page: 'events' | 'live') => void }

export default function DashboardPage({ onNavigate }: Props) {
  const [counts, setCounts] = useState<Counts | null>(null)
  const [recent, setRecent] = useState<DumpingEvent[]>([])
  const [daily, setDaily] = useState<{ label: string; count: number }[]>([])
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<DumpingEvent | null>(null)

  const load = useCallback(async () => {
    try {
      // 통계 API가 없어서 상태별 total을 따로 받아옴
      const [all, un, co, fp, latest] = await Promise.all([
        api.getEvents({ size: 1 }),
        api.getEvents({ status: 'UNCHECKED', size: 1 }),
        api.getEvents({ status: 'CONFIRMED', size: 1 }),
        api.getEvents({ status: 'FALSE_POSITIVE', size: 1 }),
        api.getEvents({ size: 200 }),
      ])
      setCounts({ ALL: all.total, UNCHECKED: un.total, CONFIRMED: co.total, FALSE_POSITIVE: fp.total })
      setRecent(latest.events.slice(0, 6))

      // 최근 7일 일별 건수 (프론트에서 집계)
      const days = Array.from({ length: 7 }, (_, i) => {
        const d = new Date()
        d.setHours(0, 0, 0, 0)
        d.setDate(d.getDate() - (6 - i))
        return d
      })
      setDaily(days.map((d) => {
        const next = new Date(d); next.setDate(d.getDate() + 1)
        const count = latest.events.filter((e) => {
          const t = parseServerDate(e.detected_at)
          return t >= d && t < next
        }).length
        return { label: `${d.getMonth() + 1}/${d.getDate()}`, count }
      }))
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [load])

  const max = Math.max(1, ...daily.map((d) => d.count))
  const reviewed = counts ? counts.CONFIRMED + counts.FALSE_POSITIVE : 0
  const precision = counts && reviewed > 0 ? Math.round((counts.CONFIRMED / reviewed) * 100) : null

  const STATS = [
    { key: 'ALL', label: '전체 이벤트', tone: 'text-zinc-100' },
    { key: 'UNCHECKED', label: '검토 대기', tone: 'text-amber-300' },
    { key: 'CONFIRMED', label: '투기 확정', tone: 'text-rose-300' },
    { key: 'FALSE_POSITIVE', label: '오탐', tone: 'text-zinc-400' },
  ] as const

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">관제 현황</h1>
          <p className="mt-1 text-sm text-zinc-500">10초마다 자동 갱신</p>
        </div>
        <button onClick={() => onNavigate('live')} className="rounded-lg bg-amber-400 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-amber-300">
          실시간 관제 시작 →
        </button>
      </header>

      {error && <p className="rounded-lg border border-rose-500/30 bg-rose-950/40 px-4 py-3 text-sm text-rose-300">{error}</p>}

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {STATS.map((s) => (
          <div key={s.key} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
            <p className="text-xs text-zinc-500">{s.label}</p>
            <p className={`mt-2 font-mono text-3xl font-semibold ${s.tone}`}>{counts ? counts[s.key] : '–'}</p>
          </div>
        ))}
        <div className="col-span-2 rounded-xl border border-zinc-800 bg-zinc-900 p-4 lg:col-span-1">
          <p className="text-xs text-zinc-500">판정 정확도 (확정 / 검토완료)</p>
          <p className="mt-2 font-mono text-3xl font-semibold text-emerald-300">{precision === null ? '–' : `${precision}%`}</p>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h2 className="text-sm font-medium text-zinc-300">최근 7일 탐지 건수</h2>
          <div className="mt-6 flex h-48 items-end gap-3">
            {daily.map((d) => (
              <div key={d.label} className="flex flex-1 flex-col items-center gap-2">
                <span className="font-mono text-xs text-zinc-400">{d.count}</span>
                <div className="w-full rounded-t bg-amber-400/80" style={{ height: `${(d.count / max) * 140}px`, minHeight: d.count ? 4 : 1 }} />
                <span className="font-mono text-[11px] text-zinc-500">{d.label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-zinc-300">최근 이벤트</h2>
            <button onClick={() => onNavigate('events')} className="text-xs text-zinc-500 hover:text-zinc-300">전체 보기 →</button>
          </div>
          <ul className="mt-3 divide-y divide-zinc-800">
            {recent.length === 0 && <li className="py-8 text-center text-sm text-zinc-500">아직 이벤트가 없어요</li>}
            {recent.map((e) => (
              <li key={e.id}>
                <button onClick={() => setSelected(e)} className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-zinc-800/40">
                  <img src={e.snapshot_path} alt="" className="h-10 w-16 rounded object-cover" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-zinc-200">{e.cctv_id} · {labelMeta(e.trash_type).name}</p>
                    <p className="text-xs text-zinc-500">{timeAgo(e.detected_at)}</p>
                  </div>
                  <StatusBadge status={e.status} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {selected && (
        <EventDetailModal event={selected} onClose={() => setSelected(null)} onUpdated={(u) => { setSelected(u); load() }} />
      )}
    </div>
  )
}
