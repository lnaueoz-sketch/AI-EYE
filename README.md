# AI-EYE — CCTV 불법투기 관제 시스템

```
AI-EYE/
├─ backend/            ← 팀 백엔드 코드 (수정 없음) + requirements.txt
│  ├─ main.py  database.py  ai_engine.py  best.pt
│  └─ requirements.txt
└─ frontend/           ← React + TypeScript + Vite + Tailwind 관제 대시보드
   └─ src/
      ├─ api/          types.ts(응답 타입) · client.ts(API 호출) · mock.ts(가짜 데이터)
      ├─ components/   BBoxOverlay · EventDetailModal · StatusBadge · Toast
      ├─ pages/        Dashboard · Events · LiveMonitor · VideoAnalysis
      └─ lib/format.ts 라벨/색상/날짜 포맷
```

---

## 1. 설치 (Windows, 처음 한 번만)

### ① Node.js
1. https://nodejs.org 에서 **LTS** 버전 설치 파일(.msi)을 받아 기본 옵션으로 설치
2. VSCode를 **완전히 껐다가 다시 켜고**, 터미널(메뉴 `터미널 > 새 터미널`)에서 확인
   ```
   node -v
   npm -v
   ```
   버전 숫자가 나오면 성공

### ② Python (백엔드 돌릴 때만 필요)
1. 터미널에서 `python --version` → **3.10 ~ 3.12**면 그대로 사용
2. 없거나 3.13 이상이면 https://www.python.org/downloads/ 에서 3.12 설치
   - 설치 첫 화면에서 **"Add python.exe to PATH" 꼭 체크**

### ③ VSCode 확장 (추천)
- **Tailwind CSS IntelliSense** — 클래스 자동완성
- **ES7+ React/Redux/React-Native snippets** — `rafce` 같은 단축 입력

---

## 2. 프론트엔드 실행

VSCode에서 `파일 > 폴더 열기` → `AI-EYE` 폴더 선택 후 터미널에서:

```
cd frontend
npm install
```
(처음 한 번만, 1~2분 걸림)

### 목업 모드 — 백엔드 없이 화면만 개발할 때
```
npm run dev:mock
```
→ 브라우저에서 http://localhost:5173 접속. 가짜 이벤트 27개로 모든 화면이 동작함.
실시간 관제 탭에 아무 mp4나 넣으면 일정 주기로 "투기 감지" 알림이 뜸.

### 실제 모드 — 백엔드와 연결
```
npm run dev
```
→ 백엔드(아래 3번)가 먼저 켜져 있어야 함.
`vite.config.ts`의 프록시가 `/api`, `/snapshots` 요청을 `127.0.0.1:8000`으로 넘겨주기 때문에 **백엔드에 CORS 설정을 안 해도 됨.**

---

## 3. 백엔드 실행 (내 컴퓨터에서 같이 테스트할 때)

새 터미널(`+` 버튼)에서:

```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

- `pip install`은 PyTorch 때문에 처음엔 꽤 오래 걸림 (수 GB)
- 처음 실행할 때 `yolov8n-pose.pt`를 인터넷에서 자동으로 받음
- http://localhost:8000/docs 에서 API를 직접 눌러볼 수 있음 (Swagger)
- 다음부터는 `cd backend` → `venv\Scripts\activate` → `uvicorn ...` 만 하면 됨

**`activate`에서 "스크립트를 실행할 수 없습니다" 오류가 나면** PowerShell에서 한 번만:
```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

## 4. 화면 구성

| 화면 | 기능 | 사용 API |
|---|---|---|
| 관제 현황 | 상태별 건수, 판정 정확도, 최근 7일 차트, 최근 이벤트 (10초 자동 갱신) | `GET /events` |
| 실시간 관제 | 영상 파일/웹캠을 재생하며 0.25~1초마다 프레임 분석, bbox 실시간 표시, 투기 확정 시 경고 | `POST /analyze-frame` |
| 이벤트 관리 | 상태 탭 필터, 페이지네이션, 상세 모달(스냅샷+bbox), 확정/오탐 판정 (5초 자동 갱신) | `GET /events`, `PATCH /events/{id}/status` |
| 영상 분석 | mp4 업로드 → 투기 시점 목록, 클릭하면 해당 시점으로 이동 | `POST /analyze-video` |

---

## 5. 백엔드 팀에 전달할 것

- `analyze-frame`의 `tracker`가 전역 1개라서 **CCTV ID가 여러 개면 상태가 섞임** → `cctv_id`별 dict로 분리 필요
- `DumpingEventTracker`가 `time.time()`(실제 시간) 기준이라 **영상 분석에서는 PC 속도에 따라 결과가 달라짐** → 영상은 `frame_idx / fps` 기준 시간으로 판단해야 함
- `status` 값 검증 없음 → `Literal["UNCHECKED","CONFIRMED","FALSE_POSITIVE"]` 권장
- 있으면 좋은 것: 통계 API, CCTV 목록 API, WebSocket 실시간 알림, 로그인

---

## 6. 자주 나는 오류

| 증상 | 원인 / 해결 |
|---|---|
| `'npm'은(는) 내부 또는 외부 명령...` | Node 설치 후 VSCode를 재시작 안 함 |
| 화면에 "백엔드 서버에 연결할 수 없어요" | uvicorn이 안 켜져 있음 → 목업 모드로 개발하거나 백엔드 실행 |
| `422 Unprocessable Entity` | 요청 형식 오류. 백엔드 `/docs`에서 같은 요청을 해보고 비교 |
| `Form data requires "python-multipart"` | `pip install python-multipart` |
| 웹캠이 안 켜짐 | 브라우저 주소가 `localhost`인지 확인 (IP 주소로 접속하면 카메라 권한이 막힘) |
| 실시간 관제가 느림 | CPU에서 모델 2개를 돌려서 프레임당 수백 ms 걸림. 간격을 1초로 늘리기 |
