"""경량 IoU 트래커: 사람에게 프레임 간 고유 ID 부여.

ultralytics의 model.track(persist=True)는 모델 객체 하나에 추적 상태가 묶여서
CCTV 여러 대가 모델을 공유하면 ID가 섞인다. 그래서 CCTV마다 이 트래커를 따로 둔다.
(12월 1주차 '객체 추적' 단계에서 ByteTrack으로 교체 가능)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


@dataclass
class _Track:
    track_id: int
    bbox: List[float]
    last_seen: float


class IoUTracker:
    def __init__(self, iou_threshold: float = 0.3, max_age_sec: float = 1.0):
        self.iou_threshold = iou_threshold
        self.max_age = max_age_sec
        self._tracks: List[_Track] = []
        self._next_id = 1

    def update(self, bboxes: List[Sequence[float]], t: float) -> List[int]:
        """bboxes 순서대로 track_id 리스트 반환."""
        self._tracks = [tr for tr in self._tracks if t - tr.last_seen <= self.max_age]
        pairs = sorted(
            ((iou(tr.bbox, b), ti, bi) for ti, tr in enumerate(self._tracks) for bi, b in enumerate(bboxes)),
            reverse=True,
        )
        assigned: List[Optional[int]] = [None] * len(bboxes)
        used_tracks = set()
        for score, ti, bi in pairs:
            if score < self.iou_threshold:
                break
            if ti in used_tracks or assigned[bi] is not None:
                continue
            tr = self._tracks[ti]
            tr.bbox, tr.last_seen = list(bboxes[bi]), t
            assigned[bi] = tr.track_id
            used_tracks.add(ti)
        for bi, tid in enumerate(assigned):
            if tid is None:
                tr = _Track(self._next_id, list(bboxes[bi]), t)
                self._next_id += 1
                self._tracks.append(tr)
                assigned[bi] = tr.track_id
        return [int(x) for x in assigned]
