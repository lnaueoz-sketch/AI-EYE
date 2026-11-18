"""투기 이벤트 조회·관리 API (관제 대시보드용)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import DumpingEvent, get_db
from ..schemas import EventDetailOut, EventPage, EventStats, EventStatus, StatusUpdate
from ..services import event_out

router = APIRouter(prefix="/api/v1/events", tags=["events"])


def _filtered(stmt, status, cctv_id, date_from, date_to):
    if status:
        stmt = stmt.where(DumpingEvent.status == status)
    if cctv_id:
        stmt = stmt.where(DumpingEvent.cctv_id == cctv_id)
    if date_from:
        stmt = stmt.where(DumpingEvent.detected_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(DumpingEvent.detected_at <= datetime.combine(date_to, time.max))
    return stmt


@router.get("", response_model=EventPage, summary="이벤트 목록 (최신순, 필터·페이지)")
def list_events(
    status: Optional[EventStatus] = None,
    cctv_id: Optional[str] = None,
    date_from: Optional[date] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[date] = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    base = _filtered(select(DumpingEvent), status, cctv_id, date_from, date_to)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(base.order_by(DumpingEvent.detected_at.desc(), DumpingEvent.id.desc())
                      .offset((page - 1) * size).limit(size)).all()
    return EventPage(total=total or 0, page=page, size=size, events=[event_out(e) for e in rows])


@router.get("/stats", response_model=EventStats, summary="통계 (Recharts용)")
def event_stats(
    cctv_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    stmt = _filtered(select(DumpingEvent.status, DumpingEvent.cctv_id, DumpingEvent.trash_type,
                            DumpingEvent.detected_at), None, cctv_id, date_from, date_to)
    rows = db.execute(stmt).all()
    return EventStats(
        total=len(rows),
        by_status=dict(Counter(r.status for r in rows)),
        by_cctv=dict(Counter(r.cctv_id for r in rows)),
        by_trash_type=dict(Counter(r.trash_type for r in rows)),
        by_date=dict(sorted(Counter(r.detected_at.date().isoformat() for r in rows).items())),
    )


@router.get("/{event_id}", response_model=EventDetailOut, summary="이벤트 상세 (탐지·포즈 결과 포함)")
def get_event(event_id: int, db: Session = Depends(get_db)):
    e = db.get(DumpingEvent, event_id)
    if e is None:
        raise HTTPException(404, "Event not found")
    return event_out(e, detail=True)


@router.patch("/{event_id}/status", summary="관제 요원 확인 처리")
def update_status(event_id: int, req: StatusUpdate, db: Session = Depends(get_db)):
    e = db.get(DumpingEvent, event_id)
    if e is None:
        raise HTTPException(404, "Event not found")
    e.status = req.status
    db.commit()
    return {"message": "Success", "event_id": event_id, "updated_status": req.status}
