"""이벤트 저장·조회 서비스."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from sqlalchemy.orm import Session

from .ai.pipeline import FrameResult
from .ai.visualize import draw
from .config import settings
from .database import Cctv, DumpingEvent
from .schemas import EventDetailOut, EventOut

MEDIA_PREFIX = "/media"  # settings.storage_dir 이 이 경로로 서빙됨


def ensure_cctv(db: Session, cctv_id: str) -> Cctv:
    cctv = db.get(Cctv, cctv_id)
    if cctv is None:  # 등록 안 된 CCTV에서 이벤트가 오면 자동 등록
        cctv = Cctv(id=cctv_id, name=cctv_id)
        db.add(cctv)
        db.flush()
    return cctv


def _save_jpg(img: np.ndarray, name: str) -> str:
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = settings.snapshot_dir / name
    if not cv2.imwrite(str(path), img):
        raise IOError(f"스냅샷 저장 실패: {path}")
    return f"snapshots/{name}"  # storage_dir 기준 상대경로


def save_event(db: Session, cctv_id: str, frame: np.ndarray, result: FrameResult, *,
               source: str = "stream", source_name: Optional[str] = None,
               video_time_sec: Optional[float] = None) -> DumpingEvent:
    ensure_cctv(db, cctv_id)
    stem = f"{cctv_id}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
    raw_rel = _save_jpg(frame, f"{stem}.jpg")
    ann_rel = _save_jpg(draw(frame, result, settings.keypoint_conf), f"{stem}_annotated.jpg")

    trash = result.event.trash or []
    top = max(trash, key=lambda t: t.confidence) if trash else None
    event = DumpingEvent(
        cctv_id=cctv_id, source=source, source_name=source_name, video_time_sec=video_time_sec,
        trash_type=top.label if top else "trash",
        confidence=round(top.confidence, 3) if top else 0.0,
        trash_bbox=[[round(v, 1) for v in t.bbox] for t in trash],
        suspect_track_id=result.event.suspect_track_id,
        snapshot_path=raw_rel, annotated_path=ann_rel,
        detail=result.to_dict(settings.keypoint_conf, include_keypoints=False),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def event_out(e: DumpingEvent, detail: bool = False):
    data = dict(
        id=e.id, cctv_id=e.cctv_id, detected_at=e.detected_at, status=e.status, source=e.source,
        source_name=e.source_name, video_time_sec=e.video_time_sec, trash_type=e.trash_type,
        confidence=e.confidence, trash_bbox=e.trash_bbox, suspect_track_id=e.suspect_track_id,
        snapshot_url=f"{MEDIA_PREFIX}/{e.snapshot_path}",
        annotated_url=f"{MEDIA_PREFIX}/{e.annotated_path}" if e.annotated_path else None,
    )
    if detail:
        return EventDetailOut(**data, detail=e.detail)
    return EventOut(**data)
