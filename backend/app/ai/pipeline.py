"""프레임 1장 처리 파이프라인. CCTV마다 StreamProcessor 하나씩 둔다."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

import numpy as np

from .event_tracker import DumpingEventTracker, EventDecision, PersonInput, TrashInput
from .models import Detection, RawPose
from .pose_features import ActionConfig, PersonPose, PoseHistory, build_person
from .tracker import IoUTracker, iou

TRASH_LABELS = {"trash", "trash_bag"}


class ModelLike(Protocol):
    def detect(self, frame: np.ndarray) -> List[Detection]: ...
    def pose(self, frame: np.ndarray) -> List[RawPose]: ...


@dataclass
class FrameResult:
    timestamp: float
    frame_size: List[int]
    detections: List[Detection]
    persons: List[PersonPose]
    event: EventDecision
    extra_person_boxes: List[List[float]] = field(default_factory=list)  # best.pt만 잡은 사람

    @property
    def trash(self) -> List[Detection]:
        return [d for d in self.detections if d.label in TRASH_LABELS]

    def to_dict(self, kpt_conf_th: float = 0.5, include_keypoints: bool = True) -> dict:
        persons = [p.to_dict(kpt_conf_th) for p in self.persons]
        if not include_keypoints:
            for p in persons:
                p.pop("keypoints", None)
        return {
            "timestamp": round(self.timestamp, 3),
            "frame_size": self.frame_size,
            "summary": {
                "person_count": len(self.persons) + len(self.extra_person_boxes),
                "trash_count": len(self.trash),
                "suspect_motion": any(p.suspect_motion for p in self.persons),
                "actions": [p.action for p in self.persons],
            },
            "detections": [d.to_dict() for d in self.detections],
            "persons": persons,
            "event": self.event.to_dict(),
        }


class StreamProcessor:
    def __init__(self, models: ModelLike, keypoint_conf: float = 0.5,
                 action_config: Optional[ActionConfig] = None, **event_kwargs):
        self.models = models
        self.kpt_th = keypoint_conf
        self.person_tracker = IoUTracker()
        self.history = PoseHistory(action_config)
        self.events = DumpingEventTracker(**event_kwargs)
        self.lock = threading.Lock()  # 같은 CCTV 프레임은 순서대로 처리

    def process(self, frame: np.ndarray, t: float) -> FrameResult:
        detections = self.models.detect(frame)
        raw_poses = self.models.pose(frame)
        with self.lock:
            return self._process(frame, t, detections, raw_poses)

    def _process(self, frame, t, detections, raw_poses) -> FrameResult:
        persons = [build_person(rp.bbox, rp.score, rp.keypoints, rp.keypoint_conf, self.kpt_th) for rp in raw_poses]
        ids = self.person_tracker.update([p.bbox for p in persons], t)
        for p, tid in zip(persons, ids):
            p.track_id = tid
            self.history.update(p, t)
        self.history.prune(t)

        # best.pt가 잡았지만 Pose 모델이 놓친 사람 → '사람 있음' 판정에만 사용
        extra = [d.bbox for d in detections
                 if d.label == "person" and all(iou(d.bbox, p.bbox) < 0.3 for p in persons)]

        person_inputs = [PersonInput(p.bbox, p.suspect_motion, p.track_id) for p in persons]
        person_inputs += [PersonInput(b) for b in extra]
        trash_inputs = [TrashInput(d.bbox, d.label, d.confidence) for d in detections if d.label in TRASH_LABELS]
        decision = self.events.update(t, person_inputs, trash_inputs)

        h, w = frame.shape[:2]
        return FrameResult(t, [int(w), int(h)], detections, persons, decision, extra)


class PipelineManager:
    """cctv_id → StreamProcessor. 모델은 모든 CCTV가 공유."""

    def __init__(self, models: ModelLike, keypoint_conf: float = 0.5,
                 action_config: Optional[ActionConfig] = None, **event_kwargs):
        self.models = models
        self.kpt_th = keypoint_conf
        self.action_config = action_config
        self.event_kwargs = event_kwargs
        self._streams: Dict[str, StreamProcessor] = {}
        self._lock = threading.Lock()

    def get(self, cctv_id: str) -> StreamProcessor:
        with self._lock:
            if cctv_id not in self._streams:
                self._streams[cctv_id] = self.new_processor()
            return self._streams[cctv_id]

    def new_processor(self) -> StreamProcessor:
        return StreamProcessor(self.models, self.kpt_th, self.action_config, **self.event_kwargs)

    def reset(self, cctv_id: Optional[str] = None):
        with self._lock:
            if cctv_id is None:
                self._streams.clear()
            else:
                self._streams.pop(cctv_id, None)

    def states(self) -> Dict[str, str]:
        with self._lock:
            return {k: v.events.state for k, v in self._streams.items()}
