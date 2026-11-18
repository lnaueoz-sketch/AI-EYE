"""분석 API: 프레임 1장 / 동영상 파일."""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import uuid
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..ai.pipeline import PipelineManager
from ..ai.visualize import draw, encode_jpeg
from ..config import settings
from ..database import get_db
from ..services import event_out, save_event

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])
ALLOWED_VIDEO = {".mp4", ".avi", ".mov", ".mkv"}


def get_manager(request: Request) -> PipelineManager:
    return request.app.state.manager


def _decode_image(upload: UploadFile) -> np.ndarray:
    data = upload.file.read()
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "이미지를 읽을 수 없습니다 (jpg/png 지원)")
    return frame


# async가 아닌 def → FastAPI가 스레드풀에서 실행하므로 YOLO 추론 중에도 서버가 멈추지 않음
@router.post("/frame", summary="프레임 1장 분석 (실시간 스트림용, CCTV별 상태 유지)")
def analyze_frame(
    file: UploadFile = File(..., description="jpg/png 프레임"),
    cctv_id: str = Query("CCTV_01"),
    timestamp: Optional[float] = Query(None, description="프레임 시각(초). 생략 시 서버 현재 시각"),
    include_keypoints: bool = Query(True, description="17개 관절 좌표 포함 여부"),
    manager: PipelineManager = Depends(get_manager),
    db: Session = Depends(get_db),
):
    frame = _decode_image(file)
    t = time.time() if timestamp is None else timestamp
    result = manager.get(cctv_id).process(frame, t)

    event = None
    if result.event.confirmed:
        event = event_out(save_event(db, cctv_id, frame, result, source="stream"))
    return {"cctv_id": cctv_id, "result": result.to_dict(settings.keypoint_conf, include_keypoints),
            "event": event}


@router.post("/frame/annotated", summary="프레임 1장 분석 결과를 그림으로 반환 (포즈 확인/데모용, 상태 저장 안 함)",
             response_class=Response, responses={200: {"content": {"image/jpeg": {}}}})
def analyze_frame_annotated(
    file: UploadFile = File(...),
    manager: PipelineManager = Depends(get_manager),
):
    frame = _decode_image(file)
    result = manager.new_processor().process(frame, 0.0)
    img = draw(frame, result, settings.keypoint_conf)
    return Response(encode_jpeg(img), media_type="image/jpeg",
                    headers={"X-Person-Count": str(len(result.persons)),
                             "X-Trash-Count": str(len(result.trash))})


@router.post("/video", summary="동영상 파일 분석 (영상 시간 기준으로 투기 판정)")
def analyze_video(
    file: UploadFile = File(..., description="mp4/avi/mov/mkv"),
    cctv_id: str = Query("CCTV_01"),
    frame_stride: int = Query(settings.video_frame_stride, ge=1, le=30, description="N프레임마다 1번 분석"),
    annotate: bool = Query(False, description="관절·박스를 그린 결과 영상 저장"),
    max_seconds: Optional[float] = Query(None, gt=0, description="앞에서부터 이 길이만 분석"),
    manager: PipelineManager = Depends(get_manager),
    db: Session = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_VIDEO:
        raise HTTPException(400, f"지원하지 않는 형식: {ext or '(없음)'}")

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    writer = None
    cap = None
    try:
        with tmp:
            shutil.copyfileobj(file.file, tmp)
        cap = cv2.VideoCapture(tmp.name)
        if not cap.isOpened():
            raise HTTPException(400, "동영상을 열 수 없습니다")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

        processor = manager.new_processor()  # 영상마다 독립된 상태
        annotated_rel = None
        if annotate:
            settings.storage_dir.joinpath("videos").mkdir(parents=True, exist_ok=True)
            annotated_rel = f"videos/{cctv_id}_{uuid.uuid4().hex[:8]}_annotated.mp4"

        events, suspect_times = [], []
        analyzed, max_persons, frame_idx = 0, 0, -1
        started = time.time()
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1
            t = frame_idx / fps  # ★ 실제 경과시간이 아니라 '영상 속 시간'으로 판정
            if max_seconds is not None and t > max_seconds:
                break
            if frame_idx % frame_stride != 0:
                continue
            result = processor.process(frame, t)
            analyzed += 1
            max_persons = max(max_persons, len(result.persons))
            if any(p.suspect_motion for p in result.persons):
                suspect_times.append(round(t, 2))

            if annotate:
                img = draw(frame, result, settings.keypoint_conf)
                if writer is None:
                    h, w = img.shape[:2]
                    writer = cv2.VideoWriter(str(settings.storage_dir / annotated_rel),
                                             cv2.VideoWriter_fourcc(*"mp4v"), fps / frame_stride, (w, h))
                writer.write(img)

            if result.event.confirmed:
                ev = save_event(db, cctv_id, frame, result, source="video",
                                source_name=file.filename, video_time_sec=round(t, 2))
                events.append(event_out(ev))

        return {
            "filename": file.filename,
            "cctv_id": cctv_id,
            "video": {"fps": round(fps, 2), "total_frames": total_frames,
                      "duration_sec": round(total_frames / fps, 2) if total_frames else None},
            "analysis": {"frame_stride": frame_stride, "analyzed_frames": analyzed,
                         "processing_sec": round(time.time() - started, 2), "max_persons_in_frame": max_persons,
                         "suspect_motion_times": _compress_times(suspect_times, gap=1.0)},
            "total_events_detected": len(events),
            "events": events,
            "annotated_video_url": f"/media/{annotated_rel}" if annotated_rel and writer is not None else None,
        }
    finally:
        if writer is not None:
            writer.release()
        if cap is not None:
            cap.release()
        try:
            os.remove(tmp.name)
        except OSError:
            pass


def _compress_times(times, gap: float):
    """[1.0,1.1,1.2,5.0] → [[1.0,1.2],[5.0,5.0]] 의심 동작 구간."""
    spans = []
    for t in times:
        if spans and t - spans[-1][1] <= gap:
            spans[-1][1] = t
        else:
            spans.append([t, t])
    return spans
