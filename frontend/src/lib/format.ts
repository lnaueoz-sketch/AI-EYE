import type { DetectedObject, EventStatus } from '../api/types'

export const STATUS_META: Record<EventStatus, { label: string; badge: string; dot: string }> = {
  UNCHECKED: { label: '미확인', badge: 'bg-amber-400/15 text-amber-300 ring-amber-400/30', dot: 'bg-amber-400' },
  CONFIRMED: { label: '투기 확정', badge: 'bg-rose-500/15 text-rose-300 ring-rose-500/30', dot: 'bg-rose-500' },
  FALSE_POSITIVE: { label: '오탐', badge: 'bg-zinc-500/15 text-zinc-400 ring-zinc-500/30', dot: 'bg-zinc-500' },
}

export const LABEL_META: Record<string, { name: string; color: string }> = {
  trash: { name: '쓰레기', color: '#f59e0b' },
  trash_bag: { name: '쓰레기봉투', color: '#f43f5e' },
  person: { name: '사람', color: '#38bdf8' },
  park_pot: { name: '화분', color: '#4ade80' },
}

export function labelMeta(label: string) {
  return LABEL_META[label] ?? { name: label, color: '#a1a1aa' }
}

export function parseBboxJson(json: string): DetectedObject[] {
  try {
    const v = JSON.parse(json)
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
}

/** 타임존 없는 ISO 문자열 → 로컬 시간으로 해석 */
export function parseServerDate(s: string): Date {
  return new Date(s.replace(' ', 'T'))
}

export function formatDateTime(s: string): string {
  const d = parseServerDate(s)
  if (isNaN(d.getTime())) return s
  return d.toLocaleString('ko-KR', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  })
}

export function timeAgo(s: string): string {
  const diff = (Date.now() - parseServerDate(s).getTime()) / 1000
  if (diff < 60) return '방금 전'
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`
  return `${Math.floor(diff / 86400)}일 전`
}

export const pct = (v: number) => `${Math.round(v * 100)}%`
