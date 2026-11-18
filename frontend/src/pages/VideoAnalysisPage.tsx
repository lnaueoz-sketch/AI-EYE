import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { AnalyzeVideoResponse } from '../api/types'
import { useToast } from '../components/Toast'

/** "12.3초 시점" → 12.3 */
const parseSec = (s: string) => parseFloat(s) || 0

export default function VideoAnalysisPage() {
  const notify = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [cctvId, setCctvId] = useState('CCTV_01')
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [result, setResult] = useState<AnalyzeVideoResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])

  useEffect(() => {
    if (!busy) return
    const t0 = Date.now()
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 500)
    return () => clearInterval(t)
  }, [busy])

  function choose(f: File | undefined) {
    if (!f) return
    if (!f.type.startsWith('video/')) {
      notify('error', '동영상 파일만 올릴 수 있어요')
      return
    }
    setFile(f)
    setPreviewUrl(URL.createObjectURL(f))
    setResult(null)
    setError(null)
  }

  async function analyze() {
    if (!file) return
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setBusy(true)
    setElapsed(0)
    setError(null)
    setResult(null)
    try {
      const res = await api.analyzeVideo(file, cctvId, ctrl.signal)
      setResult(res)
      notify(res.total_events_detected > 0 ? 'alert' : 'success', '분석 완료', `투기 이벤트 ${res.total_events_detected}건`)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  function seek(sec: number) {
    const v = videoRef.current
    if (!v) return
    v.currentTime = sec
    v.play().catch(() => {})
    v.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold text-zinc-100">영상 업로드 분석</h1>
        <p className="mt-1 text-sm text-zinc-500">녹화된 CCTV 영상을 통째로 올려 투기 시점을 찾습니다. 감지된 이벤트는 이벤트 관리에 자동 저장돼요.</p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <div className="space-y-3">
          {previewUrl ? (
            <video ref={videoRef} src={previewUrl} controls muted className="w-full rounded-xl border border-zinc-800 bg-black" />
          ) : (
            <label
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); choose(e.dataTransfer.files[0]) }}
              className={`flex aspect-video cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed text-zinc-500 transition ${
                dragOver ? 'border-amber-400 bg-amber-400/5' : 'border-zinc-700 hover:border-zinc-500'
              }`}
            >
              <span className="text-3xl">⬆</span>
              <span className="text-sm">mp4 파일을 끌어다 놓거나 클릭해서 선택</span>
              <input type="file" accept="video/*" className="hidden" onChange={(e) => choose(e.target.files?.[0])} />
            </label>
          )}

          <div className="flex flex-wrap items-center gap-2">
            {file && (
              <label className="cursor-pointer rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-400 hover:border-zinc-500">
                다른 파일
                <input type="file" accept="video/*" className="hidden" onChange={(e) => choose(e.target.files?.[0])} />
              </label>
            )}
            <span className="truncate text-sm text-zinc-400">{file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)}MB` : ''}</span>
            <input value={cctvId} onChange={(e) => setCctvId(e.target.value)} className="ml-auto w-28 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 font-mono text-sm" aria-label="CCTV ID" />
            {busy ? (
              <button onClick={() => abortRef.current?.abort()} className="rounded-lg bg-zinc-700 px-4 py-1.5 text-sm font-semibold">취소</button>
            ) : (
              <button disabled={!file} onClick={analyze} className="rounded-lg bg-amber-400 px-4 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-amber-300 disabled:opacity-40">분석 시작</button>
            )}
          </div>
          {error && <p className="rounded-lg border border-rose-500/30 bg-rose-950/40 px-4 py-2 text-sm text-rose-300">{error}</p>}
        </div>

        <aside className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <h2 className="text-xs font-medium tracking-wide text-zinc-500 uppercase">분석 결과</h2>
          {busy ? (
            <div className="flex flex-col items-center gap-3 py-12">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-amber-400" />
              <p className="text-sm text-zinc-300">AI가 영상을 분석하는 중…</p>
              <p className="font-mono text-xs text-zinc-500">{fmt(elapsed)} 경과 · 영상 길이에 따라 몇 분 걸릴 수 있어요</p>
            </div>
          ) : !result ? (
            <p className="py-12 text-center text-sm text-zinc-600">영상을 올리고 분석을 시작하세요</p>
          ) : result.events.length === 0 ? (
            <p className="py-12 text-center text-sm text-zinc-400">투기 이벤트가 감지되지 않았어요</p>
          ) : (
            <ol className="mt-3 space-y-2">
              {result.events.map((ev) => (
                <li key={ev.event_id}>
                  <button onClick={() => seek(parseSec(ev.timestamp_sec))} className="flex w-full gap-3 rounded-lg border border-zinc-800 p-2 text-left hover:border-amber-400/50">
                    <img src={ev.snapshot_path} alt="" className="h-14 w-24 rounded object-cover" />
                    <div className="text-sm">
                      <p className="font-mono font-semibold text-amber-300">{fmt(parseSec(ev.timestamp_sec))}</p>
                      <p className="text-xs text-zinc-500">이벤트 #{ev.event_id} · 클릭하면 해당 시점으로 이동</p>
                    </div>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </aside>
      </div>
    </div>
  )
}
