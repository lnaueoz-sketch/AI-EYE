"""DB 연결 + ORM 모델 (SQLAlchemy 2.0). SQLite/PostgreSQL 모두 동작."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

EVENT_STATUSES = ("UNCHECKED", "CONFIRMED", "FALSE_POSITIVE")


class Base(DeclarativeBase):
    pass


class Cctv(Base):
    __tablename__ = "cctvs"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)          # 예: CCTV_01
    name: Mapped[str] = mapped_column(String(100), default="")
    location: Mapped[str] = mapped_column(String(255), default="")         # 주소/설명
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 카카오맵 표시용
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stream_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # RTSP (추후)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    events: Mapped[list["DumpingEvent"]] = relationship(back_populates="cctv")


class DumpingEvent(Base):
    __tablename__ = "dumping_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cctv_id: Mapped[str] = mapped_column(ForeignKey("cctvs.id"), index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    status: Mapped[str] = mapped_column(String(20), default="UNCHECKED", index=True)

    source: Mapped[str] = mapped_column(String(20), default="stream")      # stream | video
    source_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 업로드 영상 파일명
    video_time_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 영상 내 시점

    trash_type: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Float)                       # 쓰레기 탐지 신뢰도 최댓값
    trash_bbox: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    suspect_track_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    snapshot_path: Mapped[str] = mapped_column(String(255))                # 원본 캡처
    annotated_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 박스·관절 그린 캡처
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)    # 탐지/포즈 원본 결과

    cctv: Mapped[Cctv] = relationship(back_populates="events")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
