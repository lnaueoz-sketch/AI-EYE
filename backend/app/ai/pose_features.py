"""YOLO-Pose 관절 좌표 → 손·팔·자세 특징 + 행동 인식 (11월 1~2주차)

numpy만 사용하므로 모델 없이 단위 테스트가 가능하다.
좌표계: 이미지 좌표 (y가 클수록 아래쪽).

COCO 17 keypoints
 0 nose, 1 l_eye, 2 r_eye, 3 l_ear, 4 r_ear,
 5 l_shoulder, 6 r_shoulder, 7 l_elbow, 8 r_elbow, 9 l_wrist, 10 r_wrist,
11 l_hip, 12 r_hip, 13 l_knee, 14 r_knee, 15 l_ankle, 16 r_ankle

행동(action) 분류 — 한 사람(track)의 최근 관절 기록으로 판단
  walking / standing   : 평상 자세
  bending              : 허리 숙임 (몸통 기울기 큼)
  crouching            : 쪼그려 앉음 (무릎 굽힘 또는 키가 평소보다 크게 줄어듦)
  placing  ★투기 의심   : 숙이거나 앉은 채 손이 지면 근처에 일정 시간 머무름 (내려놓기)
  throwing ★투기 의심   : 손목을 짧은 시간에 크게 아래로 휘두름 (던지기)
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]
SKELETON = [
    (5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16), (0, 1), (0, 2), (1, 3), (2, 4),
]
ARM_IDX = {"left": (5, 7, 9, 11), "right": (6, 8, 10, 12)}  # shoulder, elbow, wrist, hip
LEG_IDX = {"left": (11, 13, 15), "right": (12, 14, 16)}      # hip, knee, ankle

SUSPECT_ACTIONS = ("placing", "throwing")


@dataclass
class ActionConfig:
    """행동 인식 기준값. scripts/tune_actions.py 로 AI Hub 라벨에 맞춰 튜닝 → configs/action_config.json"""
    # 던지기 (손목 하강)
    motion_window_sec: float = 0.8   # 손목 궤적을 보는 시간 창
    drop_min: float = 0.45           # 창 안 손목 하강량 (몸통길이 단위)
    vy_min: float = 0.8              # 하강 속도 (몸통길이/초)
    low_hand_ratio: float = 1.0      # 손목 높이 비율 >= 이 값 → 골반 높이 이하
    # 자세
    bend_tilt_deg: float = 40.0      # 몸통 기울기(수직 기준) 이상 → 허리 숙임
    crouch_knee_deg: float = 110.0   # 무릎 각도 이하 → 쪼그려 앉음
    crouch_height_ratio: float = 0.75  # 박스 높이 / 평소 서 있을 때 높이 이하 → 쪼그려 앉음
    reach_low_ratio: float = 0.25    # (발목y - 손목y) / 평소 키 이하 → 손이 지면 근처
    # 시간 누적
    ref_window_sec: float = 6.0      # '평소 키'를 구하는 기록 길이
    placing_window_sec: float = 0.6  # 내려놓기 판단 창
    placing_min_frac: float = 0.6    # 창 안에서 (낮은 자세 + 손 지면 근처) 비율
    hold_sec: float = 1.5            # 의심 동작 표시 유지 시간
    walk_speed: float = 0.6          # 이동 속도 (몸통길이/초) 이상 → 걷기

    @classmethod
    def load(cls, path: Optional[str | Path]) -> "ActionConfig":
        if path and Path(path).exists():
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            names = {f.name for f in fields(cls)}
            return cls(**{k: v for k, v in raw.items() if k in names})
        return cls()

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CONFIG = ActionConfig()


@dataclass
class ArmState:
    side: str
    shoulder: Optional[Tuple[float, float]]
    elbow: Optional[Tuple[float, float]]
    wrist: Optional[Tuple[float, float]]
    elbow_angle: Optional[float]        # 어깨-팔꿈치-손목 각도 (deg, 180=쭉 편 팔)
    wrist_height_ratio: Optional[float]  # (손목y-어깨y)/몸통길이. 0=어깨, 1=골반, >1 골반 아래
    wrist_vy: Optional[float] = None     # 하강 속도 (몸통길이/초, +가 아래)
    wrist_drop: Optional[float] = None   # 시간창 안 하강량 (몸통길이 단위)
    downward_motion: bool = False
    low_reach: bool = False              # 손목이 무릎 높이 근처 (어깨 기준 비율 >= 1.5)

    def to_dict(self) -> dict:
        r = lambda v, n=2: None if v is None else round(float(v), n)  # noqa: E731
        pt = lambda p: None if p is None else [r(p[0], 1), r(p[1], 1)]  # noqa: E731
        return {
            "side": self.side,
            "shoulder": pt(self.shoulder), "elbow": pt(self.elbow), "wrist": pt(self.wrist),
            "elbow_angle": r(self.elbow_angle, 1),
            "wrist_height_ratio": r(self.wrist_height_ratio),
            "wrist_vy": r(self.wrist_vy), "wrist_drop": r(self.wrist_drop),
            "downward_motion": self.downward_motion, "low_reach": self.low_reach,
        }


@dataclass
class BodyState:
    torso_tilt: Optional[float] = None       # 몸통 기울기 (deg, 0=똑바로 섬, 90=수평)
    knee_angle: Optional[float] = None       # 엉덩이-무릎-발목 각도 중 작은 쪽 (deg)
    ground_y: Optional[float] = None         # 발목 y (없으면 박스 아래쪽)
    hand_ground: Optional[float] = None      # (발목y - 가장 낮은 손목y) / 기준 키. 0에 가까울수록 손이 바닥 근처
    height_ratio: Optional[float] = None     # 현재 박스 높이 / 평소 서 있을 때 높이
    speed: Optional[float] = None            # 이동 속도 (몸통길이/초)
    bending: bool = False
    crouching: bool = False
    reach_low: bool = False
    placing_frac: Optional[float] = None     # 최근 창에서 '낮은 자세 + 손 지면 근처' 비율

    def to_dict(self) -> dict:
        r = lambda v, n=2: None if v is None else round(float(v), n)  # noqa: E731
        return {
            "torso_tilt": r(self.torso_tilt, 1), "knee_angle": r(self.knee_angle, 1),
            "hand_ground": r(self.hand_ground), "height_ratio": r(self.height_ratio),
            "speed": r(self.speed), "placing_frac": r(self.placing_frac),
            "bending": self.bending, "crouching": self.crouching, "reach_low": self.reach_low,
        }


@dataclass
class PersonPose:
    bbox: List[float]                    # x1,y1,x2,y2
    score: float
    keypoints: np.ndarray                # (17,2)
    keypoint_conf: np.ndarray            # (17,)
    track_id: Optional[int] = None
    torso_length: Optional[float] = None
    arms: Dict[str, ArmState] = field(default_factory=dict)
    body: BodyState = field(default_factory=BodyState)
    action: str = "standing"             # walking|standing|bending|crouching|placing|throwing
    suspect_motion: bool = False         # 투기 의심 동작 (placing/throwing, hold_sec 동안 유지)

    def to_dict(self, kpt_conf_th: float = 0.5) -> dict:
        kps = []
        for i, name in enumerate(KEYPOINT_NAMES):
            c = float(self.keypoint_conf[i])
            x, y = self.keypoints[i]
            kps.append({"name": name, "x": round(float(x), 1), "y": round(float(y), 1),
                        "conf": round(c, 3), "visible": c >= kpt_conf_th})
        return {
            "track_id": self.track_id,
            "bbox": [round(float(v), 1) for v in self.bbox],
            "score": round(float(self.score), 3),
            "torso_length": None if self.torso_length is None else round(self.torso_length, 1),
            "keypoints": kps,
            "arms": {k: v.to_dict() for k, v in self.arms.items()},
            "body": self.body.to_dict(),
            "action": self.action,
            "suspect_motion": self.suspect_motion,
        }


def _pt(kpts: np.ndarray, conf: np.ndarray, i: int, th: float) -> Optional[Tuple[float, float]]:
    if conf[i] < th:
        return None
    x, y = float(kpts[i][0]), float(kpts[i][1])
    if x <= 0 and y <= 0:  # ultralytics는 미검출 관절을 (0,0)으로 채움
        return None
    return (x, y)


def _mid(a, b):
    if a and b:
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return a or b


def joint_angle(a, b, c) -> Optional[float]:
    """b를 꼭짓점으로 하는 a-b-c 각도(deg)."""
    if a is None or b is None or c is None:
        return None
    v1 = np.array(a) - np.array(b)
    v2 = np.array(c) - np.array(b)
    n = np.linalg.norm(v1) * np.linalg.norm(v2)
    if n < 1e-6:
        return None
    cos = float(np.clip(np.dot(v1, v2) / n, -1.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def torso_length(kpts, conf, th, bbox) -> float:
    lens = []
    for s, h in ((5, 11), (6, 12)):
        ps, ph = _pt(kpts, conf, s, th), _pt(kpts, conf, h, th)
        if ps and ph:
            lens.append(float(np.hypot(ps[0] - ph[0], ps[1] - ph[1])))
    if lens:
        return max(float(np.mean(lens)), 1.0)
    return max((bbox[3] - bbox[1]) * 0.3, 1.0)  # 관절이 안 보이면 키의 30%로 근사


def build_person(bbox, score, kpts, conf, th: float = 0.5) -> PersonPose:
    """한 프레임의 관절로 정적 특징(팔 각도·손 높이·몸통 기울기·무릎 각도) 계산."""
    kpts = np.asarray(kpts, dtype=float).reshape(17, 2)
    conf = np.asarray(conf, dtype=float).reshape(17)
    p = PersonPose(bbox=list(map(float, bbox)), score=float(score), keypoints=kpts, keypoint_conf=conf)
    p.torso_length = torso_length(kpts, conf, th, p.bbox)
    for side, (si, ei, wi, hi) in ARM_IDX.items():
        sh, el, wr = _pt(kpts, conf, si, th), _pt(kpts, conf, ei, th), _pt(kpts, conf, wi, th)
        ratio = None
        if wr is not None:
            if sh is not None:
                ratio = (wr[1] - sh[1]) / p.torso_length
            else:
                hip = _pt(kpts, conf, hi, th)
                if hip is not None:  # 어깨가 안 보이면 골반 기준
                    ratio = 1.0 + (wr[1] - hip[1]) / p.torso_length
        p.arms[side] = ArmState(side=side, shoulder=sh, elbow=el, wrist=wr,
                                elbow_angle=joint_angle(sh, el, wr), wrist_height_ratio=ratio,
                                low_reach=ratio is not None and ratio >= 1.5)

    b = p.body
    sh_mid = _mid(_pt(kpts, conf, 5, th), _pt(kpts, conf, 6, th))
    hip_mid = _mid(_pt(kpts, conf, 11, th), _pt(kpts, conf, 12, th))
    if sh_mid and hip_mid:
        dx, dy = sh_mid[0] - hip_mid[0], sh_mid[1] - hip_mid[1]
        n = float(np.hypot(dx, dy))
        if n > 1e-6:
            b.torso_tilt = float(np.degrees(np.arccos(np.clip(-dy / n, -1.0, 1.0))))
    knees = [joint_angle(_pt(kpts, conf, h, th), _pt(kpts, conf, k, th), _pt(kpts, conf, a, th))
             for h, k, a in LEG_IDX.values()]
    knees = [k for k in knees if k is not None]
    b.knee_angle = min(knees) if knees else None
    ankles = [a for a in (_pt(kpts, conf, 15, th), _pt(kpts, conf, 16, th)) if a]
    b.ground_y = max(a[1] for a in ankles) if ankles else p.bbox[3]
    return p


class PoseHistory:
    """track_id 별 기록 → 손목 하강 속도, 평소 키 대비 높이, 이동 속도, 행동 분류."""

    def __init__(self, config: Optional[ActionConfig] = None, max_age_sec: float = 3.0,
                 window_sec: Optional[float] = None):
        self.cfg = config or DEFAULT_CONFIG
        if window_sec is not None:  # 하위 호환
            self.cfg = ActionConfig(**{**self.cfg.to_dict(), "motion_window_sec": window_sec})
        self.max_age = max_age_sec
        self._wrist: Dict[int, Dict[str, Deque[Tuple[float, float]]]] = {}
        self._height: Dict[int, Deque[Tuple[float, float]]] = {}
        self._center: Dict[int, Deque[Tuple[float, float, float]]] = {}
        self._low: Dict[int, Deque[Tuple[float, bool]]] = {}
        self._last_fire: Dict[int, float] = {}
        self._last_seen: Dict[int, float] = {}

    # ── 내부 계산 ──
    def _wrist_motion(self, tid: int, person: PersonPose, t: float):
        c = self.cfg
        hist = self._wrist.setdefault(tid, {"left": deque(), "right": deque()})
        for side, arm in person.arms.items():
            q = hist[side]
            if arm.wrist_height_ratio is not None:
                q.append((t, arm.wrist_height_ratio))
            while q and t - q[0][0] > c.motion_window_sec:
                q.popleft()
            if len(q) >= 2 and q[-1][0] - q[0][0] > 1e-3 and arm.wrist_height_ratio is not None:
                ratios = [r for _, r in q]
                drop = q[-1][1] - min(ratios[:-1])
                vy = (q[-1][1] - q[0][1]) / (q[-1][0] - q[0][0])
                arm.wrist_drop, arm.wrist_vy = drop, vy
                end_low = arm.wrist_height_ratio >= c.low_hand_ratio * 0.85
                arm.downward_motion = drop >= c.drop_min and vy >= c.vy_min and end_low

    def _ref_height(self, tid: int, h: float, t: float) -> Optional[float]:
        q = self._height.setdefault(tid, deque())
        q.append((t, h))
        while q and t - q[0][0] > self.cfg.ref_window_sec:
            q.popleft()
        if len(q) < 3:
            return None
        return float(np.percentile([v for _, v in q], 90))

    def _speed(self, tid: int, person: PersonPose, t: float) -> Optional[float]:
        q = self._center.setdefault(tid, deque())
        bx = person.bbox
        q.append((t, (bx[0] + bx[2]) / 2, bx[3]))  # 발 위치 기준
        while q and t - q[0][0] > 1.0:
            q.popleft()
        if len(q) < 2 or q[-1][0] - q[0][0] < 0.2:
            return None
        d = float(np.hypot(q[-1][1] - q[0][1], q[-1][2] - q[0][2]))
        return d / (q[-1][0] - q[0][0]) / max(person.torso_length or 1.0, 1.0)

    def _posture(self, person: PersonPose, ref_h: Optional[float]):
        c, b = self.cfg, person.body
        h = person.bbox[3] - person.bbox[1]
        scale_h = ref_h or (person.torso_length or h * 0.3) / 0.3  # 기준 키
        b.height_ratio = None if ref_h is None else h / max(ref_h, 1.0)
        wrists = [a.wrist for a in person.arms.values() if a.wrist is not None]
        if wrists and b.ground_y is not None:
            lowest = max(w[1] for w in wrists)
            b.hand_ground = (b.ground_y - lowest) / max(scale_h, 1.0)
        b.bending = b.torso_tilt is not None and b.torso_tilt >= c.bend_tilt_deg
        b.crouching = ((b.knee_angle is not None and b.knee_angle <= c.crouch_knee_deg)
                       or (b.height_ratio is not None and b.height_ratio <= c.crouch_height_ratio))
        b.reach_low = b.hand_ground is not None and b.hand_ground <= c.reach_low_ratio

    def _classify(self, person: PersonPose, low_now: bool, frac: Optional[float], t: float,
                  tid: Optional[int]):
        c, b = self.cfg, person.body
        throwing = any(a.downward_motion for a in person.arms.values())
        placing = (frac is not None and frac >= c.placing_min_frac) if tid is not None else low_now
        if throwing:
            person.action = "throwing"
        elif placing:
            person.action = "placing"
        elif b.crouching:
            person.action = "crouching"
        elif b.bending:
            person.action = "bending"
        elif b.speed is not None and b.speed >= c.walk_speed:
            person.action = "walking"
        else:
            person.action = "standing"
        fired = person.action in SUSPECT_ACTIONS
        if tid is None:
            person.suspect_motion = fired
            return
        if fired:
            self._last_fire[tid] = t
        last = self._last_fire.get(tid)
        person.suspect_motion = last is not None and t - last <= c.hold_sec

    # ── 공개 API ──
    def update(self, person: PersonPose, t: float) -> PersonPose:
        if person.track_id is None:
            self._posture(person, None)
            low_now = (person.body.bending or person.body.crouching) and person.body.reach_low
            self._classify(person, low_now, None, t, None)
            return person
        tid = person.track_id
        self._last_seen[tid] = t
        self._wrist_motion(tid, person, t)
        ref_h = self._ref_height(tid, person.bbox[3] - person.bbox[1], t)
        person.body.speed = self._speed(tid, person, t)
        self._posture(person, ref_h)
        low_now = (person.body.bending or person.body.crouching) and person.body.reach_low
        q = self._low.setdefault(tid, deque())
        q.append((t, low_now))
        while q and t - q[0][0] > self.cfg.placing_window_sec:
            q.popleft()
        span_ok = len(q) >= 2 and q[-1][0] - q[0][0] >= self.cfg.placing_window_sec * 0.6
        frac = (sum(v for _, v in q) / len(q)) if span_ok else None
        person.body.placing_frac = frac
        self._classify(person, low_now, frac, t, tid)
        return person

    def prune(self, t: float) -> None:
        for tid in [k for k, v in self._last_seen.items() if t - v > self.max_age]:
            for d in (self._wrist, self._height, self._center, self._low, self._last_fire, self._last_seen):
                d.pop(tid, None)
