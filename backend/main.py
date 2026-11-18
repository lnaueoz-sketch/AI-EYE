import os, json, cv2
from datetime import datetime
import numpy as np
from fastapi import FastAPI, UploadFile, File, Query, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db, DumpingEventModel
from ai_engine import IllegalDumpingDetector, DumpingEventTracker

app = FastAPI(title="CCTV Illegal Dumping Detection API")

# 스냅샷 저장 폴더 생성 및 연결
os.makedirs("snapshots", exist_ok=True)
app.mount("/snapshots", StaticFiles(directory="snapshots"), name="snapshots")

detector = IllegalDumpingDetector(custom_model_path="best.pt")
tracker = DumpingEventTracker(retention_seconds=3.0)

class StatusUpdateRequest(BaseModel):
    status: str

# 1. 프레임 분석 및 투기 확정 시 DB 자동 저장 API
@app.post("/api/v1/analyze-frame")
async def analyze_frame(cctv_id: str = Query("CCTV_01"), file: UploadFile = File(...), db: Session = Depends(get_db)):
    bytes_data = await file.read()
    frame = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid Image Format")

    ai_result = detector.process_frame(frame)
    is_confirmed = tracker.track(ai_result)

    event_id = None
    if is_confirmed:
        filename = f"{cctv_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
        save_path = os.path.join("snapshots", filename)
        cv2.imwrite(save_path, frame)

        db_event = DumpingEventModel(
            cctv_id=cctv_id,
            snapshot_path=f"/snapshots/{filename}",
            trash_type="trash_bag" if any(o["label"] == "trash_bag" for o in ai_result["detected_objects"]) else "trash",
            confidence=max([o["confidence"] for o in ai_result["detected_objects"]], default=0.0),
            bbox_json=json.dumps(ai_result["detected_objects"])
        )
        db.add(db_event)
        db.commit()
        db.refresh(db_event)
        event_id = db_event.id

    return {"ai_result": ai_result, "event_confirmed": is_confirmed, "event_id": event_id}

# 2. 대시보드 이벤트 목록 조회 API
@app.get("/api/v1/events")
def get_events(status: str = None, page: int = 1, size: int = 10, db: Session = Depends(get_db)):
    query = db.query(DumpingEventModel)
    if status:
        query = query.filter(DumpingEventModel.status == status)
    total = query.count()
    events = query.order_by(DumpingEventModel.detected_at.desc()).offset((page-1)*size).limit(size).all()
    return {"total": total, "page": page, "events": events}

# 3. 관제 요원 전용 상태 변경 API
@app.patch("/api/v1/events/{event_id}/status")
def update_status(event_id: int, req: StatusUpdateRequest, db: Session = Depends(get_db)):
    event = db.query(DumpingEventModel).filter(DumpingEventModel.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.status = req.status
    db.commit()
    return {"message": "Success", "event_id": event_id, "updated_status": req.status}

import tempfile

# 4. MP4 동영상 파일 업로드 분석 API
@app.post("/api/v1/analyze-video")
async def analyze_video(
    cctv_id: str = Query("CCTV_01"), 
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    # 업로드된 MP4 파일 임시 저장
    temp_video_path = f"temp_{file.filename}"
    with open(temp_video_path, "wb") as buffer:
        buffer.write(await file.read())

    cap = cv2.VideoCapture(temp_video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    detected_events = []
    frame_idx = 0

    video_tracker = DumpingEventTracker(retention_seconds=3.0)

    # 비디오 프레임 순차 처리
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_idx += 1
        if frame_idx % 3 != 0:  # 연산 속도를 위해 3프레임당 1번 분석
            continue

        ai_result = detector.process_frame(frame)
        is_confirmed = video_tracker.track(ai_result)

        if is_confirmed:
            timestamp_sec = round(frame_idx / fps, 1)
            filename = f"{cctv_id}_vid_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
            save_path = os.path.join("snapshots", filename)
            cv2.imwrite(save_path, frame)

            db_event = DumpingEventModel(
                cctv_id=cctv_id,
                snapshot_path=f"/snapshots/{filename}",
                trash_type="trash_bag" if any(o["label"] == "trash_bag" for o in ai_result["detected_objects"]) else "trash",
                confidence=max([o["confidence"] for o in ai_result["detected_objects"]], default=0.0),
                bbox_json=json.dumps(ai_result["detected_objects"])
            )
            db.add(db_event)
            db.commit()
            db.refresh(db_event)

            detected_events.append({
                "event_id": db_event.id,
                "timestamp_sec": f"{timestamp_sec}초 시점",
                "snapshot_path": f"/snapshots/{filename}"
            })

    cap.release()
    if os.path.exists(temp_video_path):
        os.remove(temp_video_path)

    return {
        "filename": file.filename,
        "total_events_detected": len(detected_events),
        "events": detected_events
    }