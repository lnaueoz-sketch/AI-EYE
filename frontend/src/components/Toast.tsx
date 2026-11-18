import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

type Tone = 'info' | 'success' | 'error' | 'alert'
interface ToastItem { id: number; tone: Tone; title: string; body?: string }

const ToastCtx = createContext<(tone: Tone, title: string, body?: string) => void>(() => {})

export const useToast = () => useContext(ToastCtx)

const TONE: Record<Tone, string> = {
  info: 'border-zinc-700 bg-zinc-900',
  success: 'border-emerald-500/40 bg-emerald-950/80',
  error: 'border-rose-500/40 bg-rose-950/80',
  alert: 'border-amber-400/60 bg-amber-950/90 shadow-[0_0_30px_-5px] shadow-amber-500/40',
}

let seq = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const notify = useCallback((tone: Tone, title: string, body?: string) => {
    const id = ++seq
    setItems((xs) => [...xs, { id, tone, title, body }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), tone === 'alert' ? 7000 : 3500)
  }, [])

  return (
    <ToastCtx.Provider value={notify}>
      {children}
      <div className="fixed right-4 bottom-4 z-50 flex w-80 flex-col gap-2">
        {items.map((t) => (
          <div key={t.id} role="status" className={`rounded-lg border px-4 py-3 text-sm backdrop-blur ${TONE[t.tone]}`}>
            <p className="font-semibold text-zinc-100">{t.title}</p>
            {t.body && <p className="mt-0.5 text-zinc-400">{t.body}</p>}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}
