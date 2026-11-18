"""YOLO 모델 래퍼: best.pt(객체 탐지) + YOLO-Pose(관절).

ultralytics 모델은 스레드 안전하지 않으므로 모델별 Lock으로 추론을 직렬화한다.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import List

import numpy as np


@dataclass
class Detection:
    class_id: int
    label: str
    confidence: float
    bbox: List[float]

    def to_dict(self) -> dict:
        return {"class_id": self.class_id, "label": self.label, "confidence": round(self.confidence, 3),
                "bbox": [round(v, 1) for v in self.bbox]}


@dataclass
class RawPose:
    bbox: List[float]
    score: float
    keypoints: np.ndarray       # (17,2)
    keypoint_conf: np.ndarray   # (17,)


class YoloModels:
    def __init__(self, detect_path: str, pose_path: str, device: str = "", imgsz: int = 640,
                 detect_conf: float = 0.4, pose_conf: float = 0.4):
        from ultralytics import YOLO  # 무거운 import는 여기서

        self.detect_model = YOLO(detect_path)
        self.pose_model = YOLO(pose_path)
        self.names = dict(self.detect_model.names)  # best.pt: {0:park_pot,1:trash,2:trash_bag,3:person}
        self.device = device or None
        self.imgsz = imgsz
        self.detect_conf = detect_conf
        self.pose_conf = pose_conf
        self._dlock = threading.Lock()
        self._plock = threading.Lock()

    def warmup(self):
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        self.detect(dummy)
        self.pose(dummy)

    def detect(self, frame: np.ndarray) -> List[Detection]:
        with self._dlock:
            results = self.detect_model.predict(frame, conf=self.detect_conf, imgsz=self.imgsz,
                                                device=self.device, verbose=False)
        out: List[Detection] = []
        for r in results:
            if r.boxes is None:
                continue
            xyxy = r.boxes.xyxy.cpu().numpy()
            cls = r.boxes.cls.cpu().numpy().astype(int)
            conf = r.boxes.conf.cpu().numpy()
            for b, c, s in zip(xyxy, cls, conf):
                out.append(Detection(int(c), self.names.get(int(c), f"class_{c}"), float(s), b.tolist()))
        return out

    def pose(self, frame: np.ndarray) -> List[RawPose]:
        with self._plock:
            results = self.pose_model.predict(frame, conf=self.pose_conf, imgsz=self.imgsz,
                                              device=self.device, verbose=False)
        out: List[RawPose] = []
        for r in results:
            if r.boxes is None or r.keypoints is None or len(r.boxes) == 0:
                continue
            boxes = r.boxes.xyxy.cpu().numpy()
            scores = r.boxes.conf.cpu().numpy()
            kxy = r.keypoints.xy.cpu().numpy()
            kconf = r.keypoints.conf.cpu().numpy() if r.keypoints.conf is not None else np.ones(kxy.shape[:2])
            for b, s, k, kc in zip(boxes, scores, kxy, kconf):
                out.append(RawPose(b.tolist(), float(s), k, kc))
        return out
