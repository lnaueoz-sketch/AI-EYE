"""AI-EYE 백엔드 진입점.

실행:  uvicorn app.main:app --reload
문서:  http://localhost:8000/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .ai.models import YoloModels
from .ai.pipeline import PipelineManager
from .ai.pose_features import ActionConfig
from .config import settings
from .database import init_db
from .routers import analyze, cctvs, events

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ai-eye")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    log.info("모델 로딩: detect=%s pose=%s", settings.detect_model_path, settings.pose_model_path)
    models = YoloModels(settings.detect_model_path, settings.pose_model_path, settings.device,
                        settings.imgsz, settings.detect_conf, settings.pose_conf)
    models.warmup()
    log.info("모델 준비 완료. 클래스: %s", models.names)
    app.state.models = models
    action_cfg = ActionConfig.load(settings.action_config_path)
    log.info("행동 인식 기준값: %s", action_cfg.to_dict())
    app.state.action_config = action_cfg
    app.state.manager = PipelineManager(
        models, keypoint_conf=settings.keypoint_conf, action_config=action_cfg,
        retention_seconds=settings.retention_seconds, trash_miss_tolerance=settings.trash_miss_tolerance,
        suspect_timeout=settings.suspect_timeout, cooldown=settings.event_cooldown,
    )
    yield


app = FastAPI(title="AI-EYE: CCTV 쓰레기 무단투기 감지 API", version="0.2.0 (11월 2주차: 행동 인식)",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

settings.storage_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(settings.storage_dir)), name="media")

app.include_router(analyze.router)
app.include_router(events.router)
app.include_router(cctvs.router)


@app.get("/health", tags=["system"])
def health(request: Request):
    m = request.app.state.models
    return {"status": "ok", "detect_classes": m.names, "pose_model": settings.pose_model_path,
            "action_config": request.app.state.action_config.to_dict(),
            "streams": request.app.state.manager.states()}
