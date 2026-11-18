import time
import cv2
import numpy as np
from ultralytics import YOLO

class IllegalDumpingDetector:
    def __init__(self, custom_model_path="best.pt", pose_model_path="yolov8n-pose.pt", conf_threshold=0.35):
        # best.pt 학습 모델 및 Pose 관절 모델 로드
        self.detect_model = YOLO(custom_model_path)
        self.pose_model = YOLO(pose_model_path)
        self.conf_threshold = conf_threshold
        self.class_names = {0: "park_pot", 1: "trash", 2: "trash_bag", 3: "person"}

    def _check_throwing_motion(self, keypoints) -> bool:
        """사람 관절(손목과 골반) 좌표 기반 하향 투기 동작 감지"""
        if len(keypoints) < 13:
            return False
        left_wrist_y, right_wrist_y = keypoints[9][1].item(), keypoints[10][1].item()
        left_hip_y, right_hip_y = keypoints[11][1].item(), keypoints[12][1].item()
        
        hip_avg_y = (left_hip_y + right_hip_y) / 2 if (left_hip_y > 0 and right_hip_y > 0) else max(left_hip_y, right_hip_y)
        if hip_avg_y <= 0:
            return False
        return (left_wrist_y > hip_avg_y and left_wrist_y > 0) or (right_wrist_y > hip_avg_y and right_wrist_y > 0)

    def process_frame(self, frame: np.ndarray) -> dict:
        res = {"throwing_motion_detected": False, "detected_objects": [], "persons_detected": False, "trash_detected": False}
        
        # 1. Pose 관절 분석
        pose_results = self.pose_model(frame, conf=self.conf_threshold, verbose=False)
        for r in pose_results:
            if r.keypoints is not None and len(r.keypoints.xy) > 0:
                for kpts in r.keypoints.xy:
                    if self._check_throwing_motion(kpts):
                        res["throwing_motion_detected"] = True
                        break

        # 2. best.pt 객체 탐지
        detect_results = self.detect_model(frame, conf=self.conf_threshold, verbose=False)
        for r in detect_results:
            for box in r.boxes:
                cls_id = int(box.cls[0].item())
                label = self.class_names.get(cls_id, f"unknown_{cls_id}")
                conf = float(box.conf[0].item())
                bbox = [round(v, 2) for v in box.xyxy[0].tolist()]

                res["detected_objects"].append({"class_id": cls_id, "label": label, "confidence": round(conf, 3), "bbox": bbox})
                if label == "person":
                    res["persons_detected"] = True
                elif label in ["trash", "trash_bag"]:
                    res["trash_detected"] = True
        return res

class DumpingEventTracker:
    def __init__(self, retention_seconds=3.0):
        self.retention_seconds = retention_seconds
        self.suspect_start_time = None
        self.is_suspected = False

    def track(self, ai_result: dict) -> bool:
        """사람이 떠난 후에도 쓰레기가 3초 이상 잔류 시 불법투기 확정"""
        current_time = time.time()
        throwing, trash, person = ai_result["throwing_motion_detected"], ai_result["trash_detected"], ai_result["persons_detected"]

        if throwing and trash:
            if not self.is_suspected:
                self.is_suspected = True
                self.suspect_start_time = current_time

        if self.is_suspected and not person and trash:
            if (current_time - self.suspect_start_time) >= self.retention_seconds:
                self.is_suspected = False
                return True

        if not trash:
            self.is_suspected = False
        return False