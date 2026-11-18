"""환경 설정. 모든 값은 환경변수(.env 아님, OS 환경변수)로 덮어쓸 수 있다."""
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "yes", "on")
    return type(default)(raw)


@dataclass(frozen=True)
class Settings:
    # DB: 기본은 SQLite, PostgreSQL 사용 시 예) postgresql+psycopg2://user:pw@localhost:5432/ai_eye
    database_url: str = _env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'ai_eye.db'}")

    # 모델
    detect_model_path: str = _env("DETECT_MODEL_PATH", str(BASE_DIR / "models" / "best.pt"))
    pose_model_path: str = _env("POSE_MODEL_PATH", "yolov8n-pose.pt")  # 없으면 ultralytics가 자동 다운로드
    device: str = _env("YOLO_DEVICE", "")  # "" = 자동, "cpu", "0"(GPU0)
    imgsz: int = _env("YOLO_IMGSZ", 640)

    # 임계값
    detect_conf: float = _env("DETECT_CONF", 0.40)
    pose_conf: float = _env("POSE_CONF", 0.40)
    keypoint_conf: float = _env("KEYPOINT_CONF", 0.50)  # 이보다 낮은 관절은 '안 보임' 처리

    # 이벤트 판정 (12월 상태검증 단계에서 튜닝 예정)
    retention_seconds: float = _env("RETENTION_SECONDS", 3.0)   # 사람 이탈 후 쓰레기 잔류 시간
    trash_miss_tolerance: float = _env("TRASH_MISS_TOLERANCE", 1.0)  # 쓰레기 탐지가 이 시간 이상 끊기면 리셋
    suspect_timeout: float = _env("SUSPECT_TIMEOUT", 60.0)       # 의심 상태 최대 유지 시간
    event_cooldown: float = _env("EVENT_COOLDOWN", 10.0)         # 확정 후 중복 이벤트 방지

    # 행동 인식 기준값 (scripts/tune_actions.py 결과). 파일이 없으면 코드 기본값 사용
    action_config_path: str = _env("ACTION_CONFIG_PATH", str(BASE_DIR / "configs" / "action_config.json"))

    # 동영상 분석
    video_frame_stride: int = _env("VIDEO_FRAME_STRIDE", 3)

    # 저장소
    storage_dir: Path = field(default_factory=lambda: Path(_env("STORAGE_DIR", str(BASE_DIR / "storage"))))

    # CORS (프론트 개발 서버)
    cors_origins: str = _env("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")

    @property
    def snapshot_dir(self) -> Path:
        return self.storage_dir / "snapshots"


settings = Settings()
