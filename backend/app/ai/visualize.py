"""분석 결과를 프레임 위에 그리기 (스냅샷·데모용)."""
from __future__ import annotations

import cv2
import numpy as np

from .pipeline import TRASH_LABELS, FrameResult
from .pose_features import SKELETON

COLORS = {  # BGR
    "trash": (0, 165, 255), "trash_bag": (0, 0, 255), "park_pot": (255, 200, 0), "person": (0, 200, 0),
}
STATE_COLORS = {"IDLE": (180, 180, 180), "SUSPECT": (0, 200, 255), "COOLDOWN": (0, 0, 255)}


def draw(frame: np.ndarray, res: FrameResult, kpt_th: float = 0.5) -> np.ndarray:
    img = frame.copy()
    for d in res.detections:
        if d.label == "person":
            continue  # 사람은 포즈 박스로 표시
        x1, y1, x2, y2 = map(int, d.bbox)
        c = COLORS.get(d.label, (255, 255, 255))
        cv2.rectangle(img, (x1, y1), (x2, y2), c, 2)
        cv2.putText(img, f"{d.label} {d.confidence:.2f}", (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 2)

    for b in res.extra_person_boxes:
        x1, y1, x2, y2 = map(int, b)
        cv2.rectangle(img, (x1, y1), (x2, y2), COLORS["person"], 1)

    for p in res.persons:
        c = (0, 0, 255) if p.suspect_motion else COLORS["person"]
        x1, y1, x2, y2 = map(int, p.bbox)
        cv2.rectangle(img, (x1, y1), (x2, y2), c, 2)
        tag = f"ID{p.track_id} {p.action}" + (" !" if p.suspect_motion else "")
        cv2.putText(img, tag, (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, c, 2)
        k, kc = p.keypoints, p.keypoint_conf
        for a, b in SKELETON:
            if kc[a] >= kpt_th and kc[b] >= kpt_th:
                cv2.line(img, tuple(map(int, k[a])), tuple(map(int, k[b])), (255, 255, 0), 2)
        for i in range(17):
            if kc[i] >= kpt_th:
                r = 5 if i in (9, 10) else 3  # 손목 강조
                cv2.circle(img, tuple(map(int, k[i])), r, (0, 0, 255) if i in (9, 10) else (255, 0, 255), -1)
        for arm in p.arms.values():
            if arm.elbow is not None and arm.elbow_angle is not None:
                ex, ey = map(int, arm.elbow)
                cv2.putText(img, f"{arm.elbow_angle:.0f}", (ex + 4, ey), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                            (255, 255, 255), 1)

    ev = res.event
    color = (0, 0, 255) if ev.confirmed else STATE_COLORS.get(ev.state, (255, 255, 255))
    label = "DUMPING CONFIRMED" if ev.confirmed else ev.state
    cv2.rectangle(img, (0, 0), (260, 30), (0, 0, 0), -1)
    cv2.putText(img, f"{label}  t={res.timestamp:.1f}s", (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    return img


def encode_jpeg(img: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG 인코딩 실패")
    return buf.tobytes()


__all__ = ["draw", "encode_jpeg", "TRASH_LABELS"]
