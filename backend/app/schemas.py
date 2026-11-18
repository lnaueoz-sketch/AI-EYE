"""API 요청/응답 스키마 (Pydantic v2)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

EventStatus = Literal["UNCHECKED", "CONFIRMED", "FALSE_POSITIVE"]


class CctvCreate(BaseModel):
    id: str = Field(..., max_length=50, examples=["CCTV_01"])
    name: str = ""
    location: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    is_active: bool = True


class CctvUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    stream_url: Optional[str] = None
    is_active: Optional[bool] = None


class CctvOut(CctvCreate):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cctv_id: str
    detected_at: datetime
    status: EventStatus
    source: str
    source_name: Optional[str]
    video_time_sec: Optional[float]
    trash_type: str
    confidence: float
    trash_bbox: Optional[List[Any]]
    suspect_track_id: Optional[int]
    snapshot_url: str
    annotated_url: Optional[str]


class EventDetailOut(EventOut):
    detail: Optional[dict]


class EventPage(BaseModel):
    total: int
    page: int
    size: int
    events: List[EventOut]


class StatusUpdate(BaseModel):
    status: EventStatus


class EventStats(BaseModel):
    total: int
    by_status: dict
    by_cctv: dict
    by_trash_type: dict
    by_date: dict
