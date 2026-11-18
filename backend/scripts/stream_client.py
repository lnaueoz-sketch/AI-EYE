"""웹캠/RTSP/동영상 → /api/v1/analyze/frame 으로 프레임을 보내는 테스트 클라이언트.

사용 예)
  python scripts/stream_client.py --source 0                      # 웹캠
  python scripts/stream_client.py --source rtsp://... --cctv CCTV_02
  python scripts/stream_client.py --source sample.mp4 --show       # 영상 시간 기준으로 전송
"""
import argparse
import time

import cv2
import requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0")
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--cctv", default="CCTV_01")
    ap.add_argument("--fps", type=float, default=5.0, help="초당 전송 프레임 수")
    ap.add_argument("--show", action="store_true", help="관절 좌표를 화면에 그려서 표시")
    a = ap.parse_args()

    src = int(a.source) if a.source.isdigit() else a.source
    cap = cv2.VideoCapture(src)
    is_file = isinstance(src, str) and not src.startswith(("rtsp://", "http://"))
    vfps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(int(round(vfps / a.fps)), 1) if is_file else 1
    url = f"{a.server}/api/v1/analyze/frame"
    idx, last_sent = -1, 0.0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        if is_file:
            if idx % step:
                continue
            ts = idx / vfps                      # 영상 속 시간
        else:
            now = time.time()
            if now - last_sent < 1.0 / a.fps:
                continue
            last_sent, ts = now, now

        _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        r = requests.post(url, params={"cctv_id": a.cctv, "timestamp": ts},
                          files={"file": ("frame.jpg", jpg.tobytes(), "image/jpeg")}, timeout=30)
        r.raise_for_status()
        data = r.json()
        res, ev = data["result"], data["event"]
        print(f"t={ts:7.2f}  persons={res['summary']['person_count']}  trash={res['summary']['trash_count']}"
              f"  suspect={res['summary']['suspect_motion']}  state={res['event']['state']}"
              + (f"  ★ EVENT #{ev['id']}" if ev else ""))

        if a.show:
            for p in res["persons"]:
                for kp in p.get("keypoints", []):
                    if kp["visible"]:
                        cv2.circle(frame, (int(kp["x"]), int(kp["y"])), 3, (255, 0, 255), -1)
                x1, y1, x2, y2 = map(int, p["bbox"])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255) if p["suspect_motion"] else (0, 200, 0), 2)
            for d in res["detections"]:
                if d["label"] != "person":
                    x1, y1, x2, y2 = map(int, d["bbox"])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 165, 255), 2)
            cv2.imshow("AI-EYE", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
