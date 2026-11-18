# AI-EYE 백엔드 (FastAPI)

CCTV 쓰레기 무단투기 감지 시스템 백엔드. **11월 1주차 범위: 포즈 추정(사람 관절 좌표, 손·팔 위치 추적)**
+ best.pt 객체 탐지 연동. 이후 주차(행동 인식, 상태 검증, WebSocket 등)는 이 구조 위에 이어서 붙이면 됩니다.

## 실행

```bash
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload
```
- API 문서(Swagger): http://localhost:8000/docs (여기서 바로 이미지/영상 업로드 테스트 가능)
- 첫 실행 시 `yolov8n-pose.pt`가 자동 다운로드됩니다 (인터넷 필요).
- best.pt는 `models/best.pt`에 있습니다. (클래스: 0 park_pot, 1 trash, 2 trash_bag, 3 person)
- 로직 테스트(모델 없이): `python -m pytest -q`

## 폴더 구조

```
app/
  main.py            FastAPI 앱, 모델 로딩(lifespan), 라우터 등록
  config.py          설정값 (환경변수로 변경 가능)
  database.py        SQLAlchemy 2.0 ORM: cctvs, dumping_events
  schemas.py         요청/응답 스키마
  services.py        이벤트 저장(원본·주석 스냅샷), 응답 변환
  ai/
    models.py        best.pt + YOLO-Pose 래퍼 (스레드 Lock)
    pose_features.py ★ 관절 → 팔꿈치 각도, 손목 높이, 손목 하강 속도, 의심 동작
    tracker.py       IoU 트래커 (사람 ID 부여, CCTV별 독립)
    event_tracker.py 투기 판정 상태 머신 (IDLE → SUSPECT → 확정 → COOLDOWN)
    pipeline.py      프레임 1장 처리 흐름 + CCTV별 상태 관리
    visualize.py     박스·관절·상태 그리기
  routers/
    analyze.py       /api/v1/analyze/*
    events.py        /api/v1/events/*
    cctvs.py         /api/v1/cctvs/*
scripts/stream_client.py   웹캠/RTSP/영상 → 서버로 프레임 전송 테스트
tests/test_logic.py        포즈 특징·추적·상태머신·파이프라인 테스트
storage/                   스냅샷(/media/snapshots), 주석 영상(/media/videos)
```

## API

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/v1/analyze/frame?cctv_id=&timestamp=` | 프레임 1장 분석. CCTV별 상태 유지, 확정 시 DB 저장 |
| POST | `/api/v1/analyze/frame/annotated` | 박스·관절을 그린 JPEG 반환 (**포즈 추정 시연용**) |
| POST | `/api/v1/analyze/video?cctv_id=&frame_stride=&annotate=` | 동영상 분석. `annotate=true`면 관절 그린 결과 영상 저장 |
| GET | `/api/v1/events?status=&cctv_id=&date_from=&date_to=&page=&size=` | 이벤트 목록 |
| GET | `/api/v1/events/stats` | 상태·CCTV·쓰레기종류·날짜별 통계 (Recharts용) |
| GET | `/api/v1/events/{id}` | 이벤트 상세 (탐지·포즈 결과 포함) |
| PATCH | `/api/v1/events/{id}/status` | `UNCHECKED` / `CONFIRMED` / `FALSE_POSITIVE` |
| GET/POST/PATCH | `/api/v1/cctvs` | CCTV 등록·조회·수정 (위도/경도 → 카카오맵) |
| POST | `/api/v1/cctvs/{id}/reset-state` | 해당 CCTV 추적 상태 초기화 |
| GET | `/health` | 서버·모델 상태, CCTV별 현재 판정 상태 |

### `/analyze/frame` 응답에서 포즈 부분

```json
"persons": [{
  "track_id": 3, "bbox": [..], "score": 0.91, "torso_length": 118.4,
  "keypoints": [{"name": "left_wrist", "x": 312.5, "y": 540.1, "conf": 0.88, "visible": true}, ...17개],
  "arms": {
    "left":  {"shoulder": [..], "elbow": [..], "wrist": [..], "elbow_angle": 152.3,
              "wrist_height_ratio": 1.12, "wrist_vy": 1.4, "wrist_drop": 0.62,
              "downward_motion": true, "low_reach": false},
    "right": {...}
  },
  "suspect_motion": true
}]
```
- `wrist_height_ratio`: (손목y − 어깨y) / 몸통길이. 0 = 어깨, 1 = 골반, 1.5 이상 ≈ 무릎 (화면 크기와 무관하게 비교 가능)
- `wrist_vy`: 손목 하강 속도 (몸통길이/초, +가 아래), `wrist_drop`: 최근 0.8초 동안 하강량
- `downward_motion`: 짧은 시간에 손을 크게 내림 / `low_reach`: 허리 숙여 무릎 높이까지 손을 내림
- 신뢰도 `KEYPOINT_CONF`(기본 0.5) 미만 관절은 `visible:false`로 계산에서 제외

## 투기 판정 로직 (기존 코드 대비 수정점)

1. **시간 기준**: 동영상은 `frame_idx / fps`(영상 속 시간), 스트림은 `timestamp` 파라미터 또는 서버 시각
2. **3초는 '사람이 쓰레기 주변을 떠난 시점'부터** 계산 (화면 반대편 행인은 무시)
3. 의심 동작은 **그 사람 주변(박스 50% 확장)에 쓰레기가 있을 때만** SUSPECT
4. 쓰레기가 1초 이상 사라지면 '다시 주워감'으로 리셋 (한두 프레임 놓쳐도 유지)
5. **CCTV별로 독립된 상태**, 확정 후 10초 쿨다운으로 중복 이벤트 방지
6. YOLO 추론 엔드포인트는 `def` → 스레드풀에서 실행되어 서버가 멈추지 않음
7. confidence는 쓰레기 클래스만으로 계산, 상태값은 3가지로 검증, 임시파일 `try/finally` 정리

## 설정 (환경변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///ai_eye.db` | PostgreSQL: `postgresql+psycopg2://user:pw@localhost:5432/ai_eye` |
| `DETECT_MODEL_PATH` / `POSE_MODEL_PATH` | `models/best.pt` / `yolov8n-pose.pt` | |
| `YOLO_DEVICE` | 자동 | `cpu`, `0`(GPU) |
| `DETECT_CONF` / `POSE_CONF` / `KEYPOINT_CONF` | 0.40 / 0.40 / 0.50 | |
| `RETENTION_SECONDS` | 3.0 | 사람 이탈 후 잔류 시간 |
| `TRASH_MISS_TOLERANCE` / `EVENT_COOLDOWN` | 1.0 / 10.0 | |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | React 개발 서버 |

## 다음 주차에 손볼 곳

- **11월 2~3주 행동 인식**: `app/ai/pose_features.py` 상단 임계값(`DROP_MIN`, `VY_MIN`, `LOW_REACH_RATIO`)을
  실제 투기/정상 영상으로 튜닝. `annotate=true`로 결과 영상을 보며 조정하면 편함
- **12월 1주 객체 추적**: `tracker.py`를 ByteTrack으로 교체 (인터페이스 `update(bboxes, t) -> ids` 유지)
- **1월 3주 WebSocket**: `routers/analyze.py`에서 `result.event.confirmed`일 때 브로드캐스트 추가
- **2월 전후 10초 클립**: StreamProcessor에 프레임 링버퍼 추가

## 11월 2주차: 행동 인식

- `app/ai/pose_features.py`: 몸통 기울기·무릎 각도·평소 키 대비 높이·손–지면 거리 → 걷기/서기/숙이기/쪼그려앉기/**내려놓기**/**던지기** 분류 (굵은 것 = 투기 의심)
- API 응답 `persons[].action`, `persons[].body` 추가, 결과 이미지에 행동 이름 표시
- 기준값: `configs/action_config.json` (AI Hub 투기 클립 40개로 튜닝, 없으면 코드 기본값)
- 평가 데이터: `datasets/aihub_dump` (클립·정답 구간 `clips.json`·관절 추출 결과 `keypoints/`·튜닝 리포트 `tuning_report.json`)

| 실행 파일 | 하는 일 |
|---|---|
| `run.bat` | 서버 실행 (ultralytics 설치된 파이썬 자동 탐색) |
| `서버점검.bat` | 실제 모델로 클립 1개 처리 → `점검결과/` |
| `2주차_관절추출.bat` | 평가 클립 관절 추출 (약 25분, 이어하기 가능) |
| `python scripts/tune_actions.py --write` | 기준값 튜닝·평가 (모델 불필요) |

결과(전체 40개): 탐지율 지난주 기준 80.0% → 자세 기반 92.5%, 오탐 1분당 약 2.7회 (일상 동작 영상으로는 미측정)
주의: Windows 스마트 앱 컨트롤이 켜져 있으면 PyTorch(torch.dll)가 차단됨
