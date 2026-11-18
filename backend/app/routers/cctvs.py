"""CCTV 등록·관리 API (카카오맵 위치 표시용 좌표 포함)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import Cctv, get_db
from ..schemas import CctvCreate, CctvOut, CctvUpdate

router = APIRouter(prefix="/api/v1/cctvs", tags=["cctvs"])


@router.get("", response_model=List[CctvOut])
def list_cctvs(db: Session = Depends(get_db)):
    return db.scalars(select(Cctv).order_by(Cctv.id)).all()


@router.post("", response_model=CctvOut, status_code=201)
def create_cctv(body: CctvCreate, db: Session = Depends(get_db)):
    if db.get(Cctv, body.id):
        raise HTTPException(409, "이미 등록된 CCTV ID입니다")
    cctv = Cctv(**body.model_dump())
    db.add(cctv)
    db.commit()
    db.refresh(cctv)
    return cctv


@router.get("/{cctv_id}", response_model=CctvOut)
def get_cctv(cctv_id: str, db: Session = Depends(get_db)):
    cctv = db.get(Cctv, cctv_id)
    if cctv is None:
        raise HTTPException(404, "CCTV not found")
    return cctv


@router.patch("/{cctv_id}", response_model=CctvOut)
def update_cctv(cctv_id: str, body: CctvUpdate, db: Session = Depends(get_db)):
    cctv = db.get(Cctv, cctv_id)
    if cctv is None:
        raise HTTPException(404, "CCTV not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(cctv, k, v)
    db.commit()
    db.refresh(cctv)
    return cctv


@router.post("/{cctv_id}/reset-state", summary="해당 CCTV의 추적·판정 상태 초기화")
def reset_state(cctv_id: str, request: Request):
    request.app.state.manager.reset(cctv_id)
    return {"message": "reset", "cctv_id": cctv_id}
