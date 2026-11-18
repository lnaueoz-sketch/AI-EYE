"""투기 이벤트 상태 머신 (기존 DumpingEventTracker 개선판)

IDLE ──(의심 동작 + 그 사람 근처에 쓰레기)──▶ SUSPECT
SUSPECT ──(쓰레기 주변에서 사람 이탈 후 retention초 동안 쓰레기 잔류)──▶ 확정 → COOLDOWN
SUSPECT ──(쓰레기가 miss_tolerance초 이상 사라짐 = 다시 주워감)──▶ IDLE
SUSPECT ──(suspect_timeout 초과)──▶ IDLE
COOLDOWN ──(cooldown 경과)──▶ IDLE

시간 t는 호출자가 넘긴다. 실시간 스트림은 time.time(), 동영상은 frame_idx/fps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .tracker import iou

IDLE, SUSPECT, COOLDOWN = "IDLE", "SUSPECT", "COOLDOWN"


def expand(b: Sequence[float], ratio: float) -> List[float]:
    w, h = b[2] - b[0], b[3] - b[1]
    return [b[0] - w * ratio, b[1] - h * ratio, b[2] + w * ratio, b[3] + h * ratio]


def overlaps(a: Sequence[float], b: Sequence[float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def same_spot(a: Sequence[float], b: Sequence[float]) -> bool:
    """같은 위치의 쓰레기인지 (탐지 박스 흔들림 허용)."""
    if iou(a, b) >= 0.2:
        return True
    acx, acy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bcx, bcy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    size = max(a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1])
    return ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5 <= size * 0.5


@dataclass
class PersonInput:
    bbox: List[float]
    suspect_motion: bool = False
    track_id: Optional[int] = None


@dataclass
class TrashInput:
    bbox: List[float]
    label: str
    confidence: float


@dataclass
class EventDecision:
    state: str
    confirmed: bool = False
    reason: str = ""
    suspect_track_id: Optional[int] = None
    trash: List[TrashInput] = field(default_factory=list)
    seconds_since_person_left: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "state": self.state, "confirmed": self.confirmed, "reason": self.reason,
            "suspect_track_id": self.suspect_track_id,
            "seconds_since_person_left": None if self.seconds_since_person_left is None
            else round(self.seconds_since_person_left, 2),
            "trash": [{"label": t.label, "confidence": round(t.confidence, 3),
                       "bbox": [round(v, 1) for v in t.bbox]} for t in self.trash],
        }


class DumpingEventTracker:
    def __init__(self, retention_seconds=3.0, trash_miss_tolerance=1.0, suspect_timeout=60.0,
                 cooldown=10.0, near_ratio=0.5):
        self.retention = retention_seconds
        self.miss_tol = trash_miss_tolerance
        self.suspect_timeout = suspect_timeout
        self.cooldown = cooldown
        self.near_ratio = near_ratio
        self.reset()

    def reset(self):
        self.state = IDLE
        self.suspect_t: Optional[float] = None
        self.person_left_t: Optional[float] = None
        self.last_trash_t: Optional[float] = None
        self.cooldown_until: Optional[float] = None
        self.spot: List[TrashInput] = []
        self.suspect_track_id: Optional[int] = None

    def _trash_at_spot(self, trash: List[TrashInput]) -> List[TrashInput]:
        return [t for t in trash if any(same_spot(t.bbox, s.bbox) for s in self.spot)]

    def _person_near_spot(self, persons: List[PersonInput]) -> bool:
        return any(overlaps(expand(p.bbox, self.near_ratio), s.bbox) for p in persons for s in self.spot)

    def update(self, t: float, persons: List[PersonInput], trash: List[TrashInput]) -> EventDecision:
        if self.state == COOLDOWN:
            if t >= (self.cooldown_until or 0):
                self.reset()
            else:
                return EventDecision(COOLDOWN, reason="확정 직후 중복 방지 대기")

        if self.state == IDLE:
            for p in persons:
                if not p.suspect_motion:
                    continue
                near = [tr for tr in trash if overlaps(expand(p.bbox, self.near_ratio), tr.bbox)]
                if near:
                    self.state, self.suspect_t, self.last_trash_t = SUSPECT, t, t
                    self.spot, self.suspect_track_id, self.person_left_t = near, p.track_id, None
                    return EventDecision(SUSPECT, reason="투기 의심 동작 + 주변 쓰레기 감지",
                                         suspect_track_id=p.track_id, trash=near)
            return EventDecision(IDLE)

        # ── SUSPECT ──
        at_spot = self._trash_at_spot(trash)
        if at_spot:
            self.last_trash_t = t
            self.spot = at_spot  # 위치 갱신 (박스 흔들림 추적)
        elif t - (self.last_trash_t or t) > self.miss_tol:
            self.reset()
            return EventDecision(IDLE, reason="쓰레기가 사라짐 (다시 주워간 것으로 판단)")

        if t - (self.suspect_t or t) > self.suspect_timeout:
            self.reset()
            return EventDecision(IDLE, reason="의심 상태 시간 초과")

        if self._person_near_spot(persons):
            self.person_left_t = None
            return EventDecision(SUSPECT, reason="사람이 쓰레기 주변에 있음",
                                 suspect_track_id=self.suspect_track_id, trash=self.spot)

        if self.person_left_t is None:
            self.person_left_t = t
        elapsed = t - self.person_left_t
        if elapsed >= self.retention and at_spot:
            decision = EventDecision(SUSPECT, confirmed=True, reason=f"사람 이탈 후 {elapsed:.1f}초 쓰레기 잔류 → 투기 확정",
                                     suspect_track_id=self.suspect_track_id, trash=at_spot,
                                     seconds_since_person_left=elapsed)
            self.reset()
            self.state, self.cooldown_until = COOLDOWN, t + self.cooldown
            return decision
        return EventDecision(SUSPECT, reason="사람 이탈, 잔류 확인 중", suspect_track_id=self.suspect_track_id,
                             trash=self.spot, seconds_since_person_left=elapsed)
