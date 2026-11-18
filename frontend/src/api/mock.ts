// 백엔드 없이 화면을 개발하기 위한 가짜 API (npm run dev:mock)
import type { Api } from './client'
import type { DetectedObject, DumpingEvent, EventStatus } from './types'

const W = 640
const H = 360

function placeholderSnapshot(seed: number, bag: boolean): string {
  const hue = (seed * 47) % 360
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
<rect width="100%" height="100%" fill="hsl(${hue},8%,22%)"/>
<rect y="${H * 0.62}" width="100%" height="${H * 0.38}" fill="hsl(${hue},6%,30%)"/>
<rect x="${W * 0.08}" y="${H * 0.18}" width="${W * 0.22}" height="${H * 0.44}" fill="hsl(${hue},6%,16%)"/>
${bag
    ? `<ellipse cx="${W * 0.55}" cy="${H * 0.74}" rx="46" ry="40" fill="#3f3f46"/>`
    : `<rect x="${W * 0.5}" y="${H * 0.68}" width="70" height="44" rx="4" fill="#78716c"/>`}
<text x="12" y="22" fill="#a1a1aa" font-family="monospace" font-size="14">MOCK SNAPSHOT #${seed}</text>
</svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

function objectsFor(bag: boolean, w = W, h = H): DetectedObject[] {
  const conf = 0.55 + Math.random() * 0.4
  return [
    bag
      ? { class_id: 2, label: 'trash_bag', confidence: +conf.toFixed(3), bbox: [w * 0.55 - 50, h * 0.74 - 44, w * 0.55 + 50, h * 0.74 + 44] }
      : { class_id: 1, label: 'trash', confidence: +conf.toFixed(3), bbox: [w * 0.5 - 6, h * 0.68 - 6, w * 0.5 + 76, h * 0.68 + 50] },
  ]
}

function toLocalIso(d: Date): string {
  const pad = (n: number, l = 2) => String(n).padStart(l, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.000000`
}

const STATUSES: EventStatus[] = ['UNCHECKED', 'UNCHECKED', 'CONFIRMED', 'FALSE_POSITIVE']
let nextId = 1
const db: DumpingEvent[] = []

for (let i = 0; i < 27; i++) {
  const bag = i % 3 !== 0
  const objs = objectsFor(bag)
  const at = new Date(Date.now() - i * 6.1 * 3600_000 - Math.random() * 3600_000)
  db.push({
    id: nextId++,
    cctv_id: ['CCTV_01', 'CCTV_02', 'CCTV_03'][i % 3],
    detected_at: toLocalIso(at),
    status: STATUSES[i % 4],
    snapshot_path: placeholderSnapshot(i + 1, bag),
    trash_type: bag ? 'trash_bag' : 'trash',
    confidence: objs[0].confidence,
    bbox_json: JSON.stringify(objs),
  })
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))
let frameCount = 0

export const mockApi: Api = {
  async getEvents({ status, page = 1, size = 10 } = {}) {
    await delay(150)
    const filtered = db
      .filter((e) => !status || e.status === status)
      .sort((a, b) => b.detected_at.localeCompare(a.detected_at))
    return { total: filtered.length, page, events: filtered.slice((page - 1) * size, page * size) }
  },

  async updateStatus(eventId, status) {
    await delay(120)
    const e = db.find((x) => x.id === eventId)
    if (!e) throw new Error('Event not found')
    e.status = status
  },

  async analyzeFrame(image, cctvId) {
    await delay(180)
    frameCount++
    let w = W
    let h = H
    try {
      const bmp = await createImageBitmap(image)
      w = bmp.width
      h = bmp.height
      bmp.close()
    } catch { /* 크기 못 읽으면 기본값 */ }

    const phase = frameCount % 16 // 0~5: 사람+투기, 6~11: 쓰레기만 남음, 12: 확정
    const objs: DetectedObject[] = objectsFor(true, w, h)
    const person = phase < 6
    if (person) {
      objs.push({ class_id: 3, label: 'person', confidence: 0.88, bbox: [w * 0.3, h * 0.2, w * 0.48, h * 0.95] })
    }
    const confirmed = phase === 12
    let eventId: number | null = null
    if (confirmed) {
      eventId = nextId++
      db.push({
        id: eventId,
        cctv_id: cctvId,
        detected_at: toLocalIso(new Date()),
        status: 'UNCHECKED',
        snapshot_path: URL.createObjectURL(image),
        trash_type: 'trash_bag',
        confidence: objs[0].confidence,
        bbox_json: JSON.stringify(objs),
      })
    }
    return {
      ai_result: {
        throwing_motion_detected: person && phase > 2,
        detected_objects: objs,
        persons_detected: person,
        trash_detected: true,
      },
      event_confirmed: confirmed,
      event_id: eventId,
    }
  },

  async analyzeVideo(video, cctvId, signal) {
    await delay(2500)
    if (signal?.aborted) throw new DOMException('aborted', 'AbortError')
    const events = [4.2, 17.8].map((t, i) => {
      const id = nextId++
      const snap = placeholderSnapshot(100 + id, i === 0)
      const objs = objectsFor(i === 0)
      db.push({
        id, cctv_id: cctvId, detected_at: toLocalIso(new Date()), status: 'UNCHECKED',
        snapshot_path: snap, trash_type: i === 0 ? 'trash_bag' : 'trash',
        confidence: objs[0].confidence, bbox_json: JSON.stringify(objs),
      })
      return { event_id: id, timestamp_sec: `${t}초 시점`, snapshot_path: snap }
    })
    return { filename: video.name, total_events_detected: events.length, events }
  },
}
