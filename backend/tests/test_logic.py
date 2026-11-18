"""모델 없이 돌아가는 로직 테스트:  python -m pytest -q"""
import numpy as np

from app.ai.event_tracker import COOLDOWN, IDLE, SUSPECT, DumpingEventTracker, PersonInput, TrashInput
from app.ai.models import Detection, RawPose
from app.ai.pipeline import StreamProcessor
from app.ai.pose_features import ActionConfig, PoseHistory, build_person, joint_angle
from app.ai.tracker import IoUTracker


def make_kpts(x=100.0, top=100.0, wrist_y=None, h=200.0):
    """서 있는 사람 관절. 어깨 y=top+0.2h, 골반 y=top+0.5h. wrist_y 미지정 시 골반 높이."""
    sh, hip = top + 0.2 * h, top + 0.5 * h
    wy = hip if wrist_y is None else wrist_y
    k = np.zeros((17, 2))
    k[0] = (x, top + 0.08 * h)
    k[1], k[2], k[3], k[4] = (x - 5, top + 0.06 * h), (x + 5, top + 0.06 * h), (x - 10, top + .07 * h), (x + 10, top + .07 * h)
    k[5], k[6] = (x - 20, sh), (x + 20, sh)
    k[7], k[8] = (x - 25, (sh + wy) / 2), (x + 25, (sh + wy) / 2)
    k[9], k[10] = (x - 25, wy), (x + 25, wy)
    k[11], k[12] = (x - 15, hip), (x + 15, hip)
    k[13], k[14] = (x - 15, top + 0.75 * h), (x + 15, top + 0.75 * h)
    k[15], k[16] = (x - 15, top + h), (x + 15, top + h)
    return k, np.ones(17)


def bbox_of(x=100.0, top=100.0, h=200.0):
    return [x - 40, top, x + 40, top + h]


# ── pose_features ──
def test_joint_angle():
    assert abs(joint_angle((0, 0), (1, 0), (2, 0)) - 180) < 1e-6
    assert abs(joint_angle((0, 1), (0, 0), (1, 0)) - 90) < 1e-6
    assert joint_angle(None, (0, 0), (1, 0)) is None


def test_wrist_ratio_and_invisible_keypoints():
    k, c = make_kpts()
    p = build_person(bbox_of(), 0.9, k, c)
    assert abs(p.torso_length - np.hypot(60, 5)) < 1e-6
    assert abs(p.arms["left"].wrist_height_ratio - 60 / np.hypot(60, 5)) < 1e-6
    c[9] = 0.1  # 왼손목 안 보임
    p = build_person(bbox_of(), 0.9, k, c)
    assert p.arms["left"].wrist is None and p.arms["left"].wrist_height_ratio is None


def test_downward_motion_detected_but_not_for_standing():
    hist = PoseHistory()
    # 가만히 서 있음 (손 골반 높이) → 의심 아님
    for i in range(10):
        k, c = make_kpts()
        p = build_person(bbox_of(), 0.9, k, c); p.track_id = 1
        hist.update(p, i * 0.1)
    assert not p.suspect_motion

    # 손을 어깨 높이(140)에서 골반 아래(215)로 0.5초 만에 내림 → 하향 동작
    hist = PoseHistory()
    for i, wy in enumerate([140, 140, 155, 175, 195, 215]):
        k, c = make_kpts(wrist_y=wy)
        p = build_person(bbox_of(), 0.9, k, c); p.track_id = 1
        hist.update(p, i * 0.1)
    assert p.arms["left"].downward_motion and p.suspect_motion


def make_bent_kpts(x=100.0, top=100.0, h=200.0, wrist_to_ground=10.0, knee_bend=False):
    """허리 숙여 손을 바닥 근처로 내린 자세. 어깨가 골반 앞쪽(옆)으로 기울어짐."""
    k, c = make_kpts(x, top, h=h)
    hip_y = top + 0.5 * h
    ground = top + h
    k[5], k[6] = (x + 50, hip_y - 20), (x + 55, hip_y - 15)          # 어깨가 옆으로 → 몸통 기울기 큼
    k[0] = (x + 80, hip_y - 5)
    k[9], k[10] = (x + 70, ground - wrist_to_ground), (x + 75, ground - wrist_to_ground)
    k[7], k[8] = (x + 60, (hip_y + ground) / 2), (x + 65, (hip_y + ground) / 2)
    if knee_bend:
        k[13], k[14] = (x + 30, top + 0.7 * h), (x + 35, top + 0.7 * h)
    return k, c


def test_static_body_features():
    k, c = make_kpts()
    p = PoseHistory().update(build_person(bbox_of(), 0.9, k, c), 0.0)
    assert p.body.torso_tilt < 10 and p.body.knee_angle > 170
    assert p.action == "standing" and not p.suspect_motion
    k, c = make_bent_kpts()
    p = PoseHistory().update(build_person(bbox_of(), 0.9, k, c), 0.0)
    assert p.body.torso_tilt > 60 and p.body.bending and p.body.reach_low
    assert p.action == "placing" and p.suspect_motion   # track 없으면 한 프레임으로 판단


def test_placing_needs_duration_with_track():
    hist = PoseHistory()
    acts = []
    for i in range(10):                      # 0.0~0.9s 서 있음
        k, c = make_kpts()
        p = build_person(bbox_of(), 0.9, k, c); p.track_id = 1
        acts.append(hist.update(p, i * 0.1).action)
    k, c = make_bent_kpts()
    p = build_person(bbox_of(), 0.9, k, c); p.track_id = 1
    first = hist.update(p, 1.0)
    assert first.action != "placing"          # 숙이자마자는 아직 아님
    for i in range(11, 18):                   # 0.7초 유지
        k, c = make_bent_kpts()
        p = build_person(bbox_of(), 0.9, k, c); p.track_id = 1
        p = hist.update(p, i * 0.1)
    assert p.action == "placing" and p.suspect_motion
    for i in range(18, 22):                   # 다시 일어남 → hold 동안 의심 유지
        k, c = make_kpts()
        p = build_person(bbox_of(), 0.9, k, c); p.track_id = 1
        p = hist.update(p, i * 0.1)
    assert p.action != "placing" and p.suspect_motion
    k, c = make_kpts()
    p = build_person(bbox_of(), 0.9, k, c); p.track_id = 1
    assert not hist.update(p, 4.0).suspect_motion  # hold_sec 지나면 해제


def test_bending_without_reaching_is_not_placing():
    k, c = make_bent_kpts(wrist_to_ground=90.0)  # 숙였지만 손은 높이 있음 (예: 휴대폰 보기)
    p = PoseHistory().update(build_person(bbox_of(), 0.9, k, c), 0.0)
    assert p.body.bending and not p.body.reach_low and p.action == "bending"


def test_action_config_load(tmp_path):
    f = tmp_path / "cfg.json"
    f.write_text('{"bend_tilt_deg": 55, "unknown_key": 1}', encoding="utf-8")
    cfg = ActionConfig.load(f)
    assert cfg.bend_tilt_deg == 55 and cfg.reach_low_ratio == ActionConfig().reach_low_ratio
    assert ActionConfig.load(tmp_path / "none.json") == ActionConfig()


# ── tracker ──
def test_iou_tracker_keeps_ids():
    tr = IoUTracker()
    a, b = [0, 0, 50, 100], [200, 0, 250, 100]
    ids1 = tr.update([a, b], 0.0)
    ids2 = tr.update([[205, 0, 255, 100], [3, 0, 53, 100]], 0.1)
    assert ids2 == [ids1[1], ids1[0]]
    ids3 = tr.update([[0, 0, 50, 100]], 5.0)  # 오래 안 보이면 새 ID
    assert ids3[0] not in ids1


# ── event state machine ──
TRASH = [TrashInput([110, 280, 140, 310], "trash_bag", 0.8)]
PERSON_NEAR = PersonInput(bbox_of(), False, 1)


def test_confirm_after_person_leaves():
    ev = DumpingEventTracker(retention_seconds=3, trash_miss_tolerance=1, cooldown=10)
    assert ev.update(0.0, [PersonInput(bbox_of(), True, 1)], TRASH).state == SUSPECT
    assert ev.update(1.0, [PERSON_NEAR], TRASH).state == SUSPECT
    # 사람 떠남 (t=2) → 3초 뒤(t=5) 확정. 의심 시작(t=0)이 아니라 이탈 시점부터 셈
    assert not ev.update(2.0, [], TRASH).confirmed
    assert not ev.update(4.9, [], TRASH).confirmed
    d = ev.update(5.0, [], TRASH)
    assert d.confirmed and d.suspect_track_id == 1
    assert ev.update(6.0, [], TRASH).state == COOLDOWN


def test_far_person_does_not_block():
    ev = DumpingEventTracker(retention_seconds=3)
    ev.update(0.0, [PersonInput(bbox_of(), True, 1)], TRASH)
    far = PersonInput([900, 100, 980, 300])
    ev.update(1.0, [far], TRASH)
    assert ev.update(4.0, [far], TRASH).confirmed


def test_pickup_resets():
    ev = DumpingEventTracker(retention_seconds=3, trash_miss_tolerance=1)
    ev.update(0.0, [PersonInput(bbox_of(), True, 1)], TRASH)
    ev.update(1.0, [], TRASH)
    ev.update(1.5, [], [])          # 한 프레임 놓침 → 아직 유지
    assert ev.state == SUSPECT
    assert ev.update(2.6, [], []).state == IDLE  # 1초 넘게 사라짐 → 주워감


def test_person_returns_restarts_timer():
    ev = DumpingEventTracker(retention_seconds=3)
    ev.update(0.0, [PersonInput(bbox_of(), True, 1)], TRASH)
    ev.update(1.0, [], TRASH)
    ev.update(2.5, [PERSON_NEAR], TRASH)   # 다시 돌아옴
    assert not ev.update(4.5, [], TRASH).confirmed  # 이탈 재시작 t=4.5
    assert ev.update(7.5, [], TRASH).confirmed


def test_no_suspect_without_motion_or_far_trash():
    ev = DumpingEventTracker()
    assert ev.update(0.0, [PERSON_NEAR], TRASH).state == IDLE
    far_trash = [TrashInput([900, 900, 950, 950], "trash", 0.9)]
    assert ev.update(1.0, [PersonInput(bbox_of(), True, 1)], far_trash).state == IDLE


# ── pipeline (가짜 모델) ──
class FakeModels:
    def __init__(self, script):
        self.script, self.i = script, 0

    def detect(self, frame):
        return self.script[self.i][0]

    def pose(self, frame):
        out = self.script[self.i][1]
        self.i += 1
        return out


def test_pipeline_end_to_end():
    trash_det = Detection(2, "trash_bag", 0.8, [110, 280, 140, 310])
    script = []
    for wy in [140, 140, 160, 185, 205, 220]:       # 0.0~0.5s 손 내림
        k, c = make_kpts(wrist_y=wy)
        script.append(([trash_det], [RawPose(bbox_of(), 0.9, k, c)]))
    for _ in range(40):                                  # 0.6~4.5s 사람 없음, 쓰레기 남음
        script.append(([trash_det], []))
    sp = StreamProcessor(FakeModels(script), retention_seconds=3.0)
    frame = np.zeros((480, 640, 3), np.uint8)
    confirmed_at = None
    for i in range(len(script)):
        r = sp.process(frame, i * 0.1)
        if r.event.confirmed:
            confirmed_at = round(r.timestamp, 1)
            d = r.to_dict()
            assert d["event"]["confirmed"] and d["summary"]["trash_count"] == 1
            break
    assert confirmed_at == 3.6  # 사람 이탈 0.6s + 3.0s

    from app.ai.visualize import draw, encode_jpeg
    assert encode_jpeg(draw(frame, r))[:2] == b"\xff\xd8"
