import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { DumpingEvent, EventStatus } from '../api/types'
import { formatDateTime, labelMeta, parseBboxJson, pct } from '../lib/format'
import BBoxOverlay from './BBoxOverlay'
import StatusBadge from './StatusBadge'
import { useToast } from './Toast'

interface Props {
  event: DumpingEvent
  onClose: () => void
  onUpdated: (e: DumpingEvent) => void
}

export default function EventDetailModal({ event, onClose, onUpdated }: Props) {
  const notify = useToast()
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [saving, setSaving] = useState<EventStatus | null>(null)
  const [showBoxes, setShowBoxes] = useState(true)
  const objects = parseBboxJson(event.bbox_json)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function setStatus(status: EventStatus) {
    setSaving(status)
    try {
      await api.updateStatus(event.id, status)
      onUpdated({ ...event, status })
      notify('success', `#${event.id} 상태 변경`, status === 'CONFIRMED' ? '투기 확정으로 처리했어요' : status === 'FALSE_POSITIVE' ? '오탐으로 처리했어요' : '미확인으로 되돌렸어요')
    } catch (e) {
      notify('error', '상태 변경 실패', (e as Error).message)
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900 lg:flex-row"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 스냅샷 */}
        <div className="flex flex-1 items-center justify-center bg-black p-3">
          <div className="relative w-full">
            <img
              src={event.snapshot_path}
              alt={`이벤트 ${event.id} 스냅샷`}
              className="block h-auto w-full"
              onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
            />
            {showBoxes && <BBoxOverlay objects={objects} width={size.w} height={size.h} />}
          </div>
        </div>

        {/* 정보 패널 */}
        <aside className="flex w-full flex-col gap-5 overflow-y-auto border-t border-zinc-800 p-5 lg:w-80 lg:border-t-0 lg:border-l">
          <div className="flex items-start justify-between">
            <div>
              <p className="font-mono text-xs text-zinc-500">EVENT #{event.id}</p>
              <h2 className="mt-1 text-lg font-semibold text-zinc-100">{event.cctv_id}</h2>
            </div>
            <button onClick={onClose} className="rounded-md px-2 py-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200" aria-label="닫기">✕</button>
          </div>

          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-zinc-500">탐지 시각</dt><dd className="font-mono text-zinc-200">{formatDateTime(event.detected_at)}</dd>
            <dt className="text-zinc-500">종류</dt><dd>{labelMeta(event.trash_type).name}</dd>
            <dt className="text-zinc-500">최고 신뢰도</dt><dd className="font-mono">{pct(event.confidence)}</dd>
            <dt className="text-zinc-500">상태</dt><dd><StatusBadge status={event.status} /></dd>
          </dl>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-medium tracking-wide text-zinc-500 uppercase">탐지 객체 {objects.length}</h3>
              <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                <input type="checkbox" checked={showBoxes} onChange={(e) => setShowBoxes(e.target.checked)} className="accent-amber-400" />
                박스 표시
              </label>
            </div>
            <ul className="space-y-1">
              {objects.map((o, i) => (
                <li key={i} className="flex items-center justify-between rounded-md bg-zinc-800/60 px-3 py-1.5 text-sm">
                  <span className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: labelMeta(o.label).color }} />
                    {labelMeta(o.label).name}
                  </span>
                  <span className="font-mono text-zinc-400">{pct(o.confidence)}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-auto space-y-2">
            <h3 className="text-xs font-medium tracking-wide text-zinc-500 uppercase">관제 판정</h3>
            <div className="grid grid-cols-2 gap-2">
              <button
                disabled={!!saving || event.status === 'CONFIRMED'}
                onClick={() => setStatus('CONFIRMED')}
                className="rounded-lg bg-rose-600 px-3 py-2.5 text-sm font-semibold text-white hover:bg-rose-500 disabled:opacity-40"
              >
                {saving === 'CONFIRMED' ? '저장 중…' : '투기 확정'}
              </button>
              <button
                disabled={!!saving || event.status === 'FALSE_POSITIVE'}
                onClick={() => setStatus('FALSE_POSITIVE')}
                className="rounded-lg bg-zinc-700 px-3 py-2.5 text-sm font-semibold text-zinc-100 hover:bg-zinc-600 disabled:opacity-40"
              >
                {saving === 'FALSE_POSITIVE' ? '저장 중…' : '오탐'}
              </button>
            </div>
            {event.status !== 'UNCHECKED' && (
              <button disabled={!!saving} onClick={() => setStatus('UNCHECKED')} className="w-full text-xs text-zinc-500 hover:text-zinc-300">
                미확인으로 되돌리기
              </button>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
