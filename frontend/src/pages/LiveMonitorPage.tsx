import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { AiResult } from '../api/types'
import BBoxOverlay from '../components/BBoxOverlay'
import { useToast } from '../components/Toast'

type Source = 'file' | 'webcam'
interface LogItem { at: Date; eventId: number | null; snapshot: string }

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/**
 * 실시간 관제 시뮬레이션
 * 브라우저에서 영상(파일 또는 웹캠)을 재생하면서 일정 간격으로 프레임을 잘라
 * POST /api/v1/analyze-frame 으로 보내고, 결과 bbox를 영상 위에 그린다.
 */
export default function LiveMonitorPage() {
  const notify = useToast()
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const fileUrlRef = useRef<string | null>(null)
  const runningRef = useRef(false)

  const [source, setSource] = useState<Source>('file')
  const [fileName, setFileName] = useState<string | null>(null)
  const [cctvId, setCctvId] = useState('CCTV_01')
  const [intervalMs, setIntervalMs] = useState(500)
  const [running, setRunning] = useState(false)
  const [ready, setReady] = useState(false)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [result, setResult] = useState<AiResult | null>(null)
  const [latency, setLatency] = useState<number | null>(null)
  const [frames, setFrames] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [log, setLog] = useState<LogItem[]>([])

  const cfg = useRef({ cctvId, intervalMs })
  cfg.current = { cctvId, intervalMs }

  function stopWebcam() {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }

  useEffect(() => () => {
    runningRef.current = false
    stopWebcam()
    if (fileUrlRef.current) URL.revokeObjectURL(fileUrlRef.current)
  }, [])

  function stop() {
    runningRef.current = false
    setRunning(false)
  }

  function pickFile(f: File | undefined) {
    if (!f) return
    stop()
    stopWebcam()
    if (fileUrlRef.current) URL.revokeObjectURL(fileUrlRef.current)
    const url = URL.createObjectURL(f)
    fileUrlRef.current = url
    const v = videoRef.current!
    v.srcObject = null
    v.src = url
    v.loop = true
    setFileName(f.name)
    setResult(null)
  }

  async function openWebcam() {
    stop()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: false })
      streamRef.current = stream
      const v = videoRef.current!
      v.removeAttribute('src')
      v.srcObject = stream
      await v.play()
      setResult(null)
    } catch (e) {
      notify('error', '웹캠을 열 수 없어요', (e as Error).message)
    }
  }

  function captureFrame(): Promise<Blob | null> {
    const v = videoRef.current!
    const c = canvasRef.current!
    c.width = v.videoWidth
    c.height = v.videoHeight
    c.getContext('2d')!.drawImage(v, 0, 0)
    return new Promise((resolve) => c.toBlob(resolve, 'image/jpeg', 0.85))
  }

  async function loop() {
    while (runningRef.current) {
      const t0 = performance.now()
      const v = videoRef.current
      if (v && v.readyState >= 2 && !v.paused) {
        const blob = await captureFrame()
        if (blob) {
          try {
            const res = await api.analyzeFrame(blob, cfg.current.cctvId)
            if (!runningRef.current) break
            setResult(res.ai_result)
            setLatency(Math.round(performance.now() - t0))
            setFrames((n) => n + 1)
            setError(null)
            if (res.event_confirmed) {
              const snap = URL.createObjectURL(blob)
              setLog((xs) => [{ at: new Date(), eventId: res.event_id, snapshot: snap }, ...xs].slice(0, 30))
              notify('alert', '🚨 불법투기 감지', `${cfg.current.cctvId} · 이벤트 #${res.event_id ?? '?'} 저장됨`)
            }
          } catch (e) {
            setError((e as Error).message)
            await sleep(1500) // 서버 오류 시 잠깐 쉬었다가 재시도
          }
        }
      }
      const wait = cfg.current.intervalMs - (performance.now() - t0)
      if (wait > 0) await sleep(wait)
    }
  }

  async function start() {
    const v = videoRef.current
    if (!v || (!v.src && !v.srcObject)) {
      notify('info', '먼저 영상 소스를 선택해 주세요')
      return
    }
    if (v.paused) await v.play().catch(() => {})
    runningRef.current = true
    setRunning(true)
    setFrames(0)
    loop()
  }

  const lamps = [
    { on: !!result?.persons_detected, label: '사람', color: 'bg-sky-400' },
    { on: !!result?.trash_detected, label: '쓰레기', color: 'bg-amber-400' },
    { on: !!result?.throwing_motion_detected, label: '투기 동작', color: 'bg-rose-500' },
  ]

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold text-zinc-100">실시간 관제</h1>
        <p className="mt-1 text-sm text-zinc-500">영상 파일이나 웹캠을 CCTV처럼 재생하면서 프레임 단위로 AI 분석을 돌립니다.</p>
      </header>

      <div className="grid gap-5 xl:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          {/* 컨트롤 바 */}
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900 p-3">
            <div className="flex rounded-lg bg-zinc-800 p-0.5 text-sm">
              {(['file', 'webcam'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => { setSource(s); if (s === 'webcam') openWebcam() }}
                  className={`rounded-md px-3 py-1.5 ${source === s ? 'bg-zinc-950 text-zinc-100' : 'text-zinc-400'}`}
                >
                  {s === 'file' ? '영상 파일' : '웹캠'}
                </button>
              ))}
            </div>
            {source === 'file' && (
              <label className="cursor-pointer rounded-lg border border-dashed border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:border-zinc-500">
                {fileName ?? 'mp4 선택…'}
                <input type="file" accept="video/*" className="hidden" onChange={(e) => pickFile(e.target.files?.[0])} />
              </label>
            )}
            <input
              value={cctvId}
              onChange={(e) => setCctvId(e.target.value)}
              className="w-28 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 font-mono text-sm"
              aria-label="CCTV ID"
            />
            <select
              value={intervalMs}
              onChange={(e) => setIntervalMs(Number(e.target.value))}
              className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm"
              aria-label="분석 간격"
            >
              <option value={250}>0.25초 간격</option>
              <option value={500}>0.5초 간격</option>
              <option value={1000}>1초 간격</option>
            </select>
            <div className="ml-auto">
              {running ? (
                <button onClick={stop} className="rounded-lg bg-zinc-700 px-4 py-1.5 text-sm font-semibold hover:bg-zinc-600">■ 정지</button>
              ) : (
                <button onClick={start} className="rounded-lg bg-amber-400 px-4 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-amber-300">▶ 분석 시작</button>
              )}
            </div>
          </div>

          {/* 영상 + bbox */}
          <div className="relative overflow-hidden rounded-xl border border-zinc-800 bg-black">
            <div className="relative">
              <video
                ref={videoRef}
                muted
                playsInline
                controls={source === 'file'}
                className={ready ? 'block h-auto w-full' : 'hidden'}
                onLoadedMetadata={(e) => { setSize({ w: e.currentTarget.videoWidth, h: e.currentTarget.videoHeight }); setReady(true) }}
              />
              {result && running && <BBoxOverlay objects={result.detected_objects} width={size.w} height={size.h} />}
            </div>
            {!ready && (
              <div className="flex aspect-video items-center justify-center text-sm text-zinc-600">영상 소스를 선택하세요</div>
            )}
            {running && (
              <div className="absolute top-3 left-3 flex items-center gap-2 rounded bg-black/70 px-2 py-1 font-mono text-xs">
                <span className="h-2 w-2 animate-pulse rounded-full bg-rose-500" /> LIVE · {cctvId}
              </div>
            )}
          </div>
          <canvas ref={canvasRef} className="hidden" />
          {error && <p className="rounded-lg border border-rose-500/30 bg-rose-950/40 px-4 py-2 text-sm text-rose-300">{error}</p>}
        </div>

        {/* 사이드 패널 */}
        <aside className="space-y-4">
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
            <h2 className="text-xs font-medium tracking-wide text-zinc-500 uppercase">AI 상태</h2>
            <ul className="mt-3 space-y-2">
              {lamps.map((l) => (
                <li key={l.label} className="flex items-center justify-between text-sm">
                  <span className="text-zinc-300">{l.label}</span>
                  <span className={`h-3 w-3 rounded-full transition ${l.on ? `${l.color} shadow-[0_0_10px] shadow-current` : 'bg-zinc-700'}`} />
                </li>
              ))}
            </ul>
            <dl className="mt-4 grid grid-cols-2 gap-2 border-t border-zinc-800 pt-3 font-mono text-xs">
              <dt className="text-zinc-500">분석 프레임</dt><dd className="text-right text-zinc-300">{frames}</dd>
              <dt className="text-zinc-500">응답 시간</dt><dd className="text-right text-zinc-300">{latency === null ? '–' : `${latency}ms`}</dd>
              <dt className="text-zinc-500">객체 수</dt><dd className="text-right text-zinc-300">{result?.detected_objects.length ?? '–'}</dd>
            </dl>
          </div>

          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
            <h2 className="text-xs font-medium tracking-wide text-zinc-500 uppercase">감지 로그</h2>
            {log.length === 0 ? (
              <p className="py-6 text-center text-sm text-zinc-600">아직 확정된 투기 없음</p>
            ) : (
              <ul className="mt-3 max-h-[420px] space-y-2 overflow-y-auto">
                {log.map((l, i) => (
                  <li key={i} className="flex gap-3 rounded-lg border border-rose-500/30 bg-rose-950/30 p-2">
                    <img src={l.snapshot} alt="" className="h-12 w-20 rounded object-cover" />
                    <div className="text-xs">
                      <p className="font-semibold text-rose-300">이벤트 #{l.eventId ?? '?'}</p>
                      <p className="font-mono text-zinc-400">{l.at.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
