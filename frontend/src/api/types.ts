// 백엔드(main.py) 응답 형태를 그대로 옮긴 타입

export type EventStatus = 'UNCHECKED' | 'CONFIRMED' | 'FALSE_POSITIVE'

export type ObjectLabel = 'park_pot' | 'trash' | 'trash_bag' | 'person' | `unknown_${number}`

export interface DetectedObject {
  class_id: number
  label: ObjectLabel
  confidence: number
  /** [x1, y1, x2, y2] — 원본 이미지 픽셀 좌표 */
  bbox: [number, number, number, number]
}

export interface AiResult {
  throwing_motion_detected: boolean
  detected_objects: DetectedObject[]
  persons_detected: boolean
  trash_detected: boolean
}

/** POST /api/v1/analyze-frame */
export interface AnalyzeFrameResponse {
  ai_result: AiResult
  event_confirmed: boolean
  event_id: number | null
}

/** DB의 dumping_events 한 행 */
export interface DumpingEvent {
  id: number
  cctv_id: string
  /** 타임존 없는 서버 로컬 시간 (예: 2026-11-11T11:24:00.123456) */
  detected_at: string
  status: EventStatus
  snapshot_path: string
  trash_type: 'trash' | 'trash_bag'
  confidence: number
  /** DetectedObject[] 를 JSON 문자열로 저장한 것 → parseBboxJson()으로 파싱 */
  bbox_json: string
}

/** GET /api/v1/events */
export interface EventsResponse {
  total: number
  page: number
  events: DumpingEvent[]
}

/** POST /api/v1/analyze-video */
export interface AnalyzeVideoResponse {
  filename: string
  total_events_detected: number
  events: {
    event_id: number
    timestamp_sec: string // "12.3초 시점"
    snapshot_path: string
  }[]
}

export interface EventsQuery {
  status?: EventStatus
  page?: number
  size?: number
}
