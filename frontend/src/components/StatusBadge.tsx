import type { EventStatus } from '../api/types'
import { STATUS_META } from '../lib/format'

export default function StatusBadge({ status }: { status: EventStatus }) {
  const m = STATUS_META[status] ?? STATUS_META.UNCHECKED
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${m.badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${m.dot}`} />
      {m.label}
    </span>
  )
}
