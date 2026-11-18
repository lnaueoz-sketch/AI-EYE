import type {
  AnalyzeFrameResponse,
  AnalyzeVideoResponse,
  EventStatus,
  EventsQuery,
  EventsResponse,
} from './types'
import { mockApi } from './mock'

export interface Api {
  getEvents(q?: EventsQuery): Promise<EventsResponse>
  updateStatus(eventId: number, status: EventStatus): Promise<void>
  analyzeFrame(image: Blob, cctvId: string): Promise<AnalyzeFrameResponse>
  analyzeVideo(video: File, cctvId: string, signal?: AbortSignal): Promise<AnalyzeVideoResponse>
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, init)
  } catch {
    throw new ApiError(0, '백엔드 서버에 연결할 수 없어요. (uvicorn이 8000번 포트에서 실행 중인지 확인)')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* 본문이 JSON이 아님 */
    }
    throw new ApiError(res.status, `${res.status} ${detail}`)
  }
  return res.json() as Promise<T>
}

const realApi: Api = {
  getEvents({ status, page = 1, size = 10 } = {}) {
    const p = new URLSearchParams({ page: String(page), size: String(size) })
    if (status) p.set('status', status)
    return request<EventsResponse>(`/api/v1/events?${p}`)
  },

  async updateStatus(eventId, status) {
    await request(`/api/v1/events/${eventId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
  },

  analyzeFrame(image, cctvId) {
    const form = new FormData()
    form.append('file', image, 'frame.jpg')
    return request<AnalyzeFrameResponse>(
      `/api/v1/analyze-frame?cctv_id=${encodeURIComponent(cctvId)}`,
      { method: 'POST', body: form },
    )
  },

  analyzeVideo(video, cctvId, signal) {
    const form = new FormData()
    form.append('file', video, video.name)
    return request<AnalyzeVideoResponse>(
      `/api/v1/analyze-video?cctv_id=${encodeURIComponent(cctvId)}`,
      { method: 'POST', body: form, signal },
    )
  },
}

// npm run dev:mock (--mode mock) 으로 실행하면 목업 모드
export const USE_MOCK = import.meta.env.MODE === 'mock' || import.meta.env.VITE_USE_MOCK === 'true'

export const api: Api = USE_MOCK ? mockApi : realApi
