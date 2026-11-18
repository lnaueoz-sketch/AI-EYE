"""행동 인식 기준값 튜닝·평가 (AI Hub 투기 라벨 기준)

모델이 필요 없다: scripts/extract_keypoints.py 가 저장한 관절 결과만 사용 (numpy).

사용:
  python scripts/tune_actions.py --dataset datasets/aihub_dump            # 평가 + 튜닝 + 리포트
  python scripts/tune_actions.py --dataset ... --eval-only                # 현재 configs/action_config.json 만 평가
  python scripts/tune_actions.py --dataset ... --write                    # 튜닝 결과를 configs/action_config.json 에 저장

평가 방법
  - 정답: AI Hub xml 의 drop 구간 (클립 기준 초)
  - 탐지 성공: drop 구간 ±1초 안에 '투기 의심(placing/throwing)'이 한 번이라도 켜짐
  - 오탐: drop 구간 ±3초 밖에서 켜진 구간 수 (2초 이내로 붙은 건 하나로 셈) → 1분당 횟수
  - 과적합 확인: 155-* 장면으로 튜닝, 157-* 장면으로 검증
"""
import argparse
import itertools
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai.pose_features import ActionConfig, PoseHistory, build_person  # noqa: E402
from app.ai.tracker import IoUTracker  # noqa: E402

POSE_SCORE_TH = 0.40
KPT_TH = 0.50
HIT_MARGIN, FP_MARGIN, MERGE_GAP = 1.0, 3.0, 2.0


# ── 1) 관절 → 사람별 특징 시계열 (기준값과 무관한 부분만, 클립당 한 번) ──
def load_features(kp_file: Path, base: ActionConfig):
    hist = PoseHistory(base)
    tracker = IoUTracker()
    tracks = {}
    times = []
    for line in kp_file.read_text(encoding="utf-8").splitlines():
        fr = json.loads(line)
        t = fr["t"]
        times.append(t)
        poses = [p for p in fr["poses"] if p["score"] >= POSE_SCORE_TH]
        persons = []
        for p in poses:
            kp = np.array(p["kp"], dtype=float)
            persons.append(build_person(p["bbox"], p["score"], kp[:, :2], kp[:, 2], KPT_TH))
        ids = tracker.update([p.bbox for p in persons], t)
        for p, tid in zip(persons, ids):
            p.track_id = tid
            hist.update(p, t)
            b = p.body
            row = (t, np.nan if b.torso_tilt is None else b.torso_tilt,
                   np.nan if b.knee_angle is None else b.knee_angle,
                   np.nan if b.hand_ground is None else b.hand_ground,
                   np.nan if b.height_ratio is None else b.height_ratio,
                   max([a.wrist_drop or 0 for a in p.arms.values()] + [0]),
                   max([a.wrist_vy or 0 for a in p.arms.values()] + [0]),
                   max([a.wrist_height_ratio or 0 for a in p.arms.values()] + [0]),
                   float(any(a.low_reach for a in p.arms.values())))
            tracks.setdefault(tid, []).append(row)
        hist.prune(t)
    return np.array(times), {k: np.array(v) for k, v in tracks.items()}


# ── 2) 기준값 적용 (벡터 연산) ──
def fire_times(tracks, cfg: ActionConfig, mode: str = "v2"):
    fired = []
    for arr in tracks.values():
        t, tilt, knee, hg, hr, drop, vy, wr, lowreach = arr.T
        throwing = (drop >= cfg.drop_min) & (vy >= cfg.vy_min) & (wr >= cfg.low_hand_ratio * 0.85)
        if mode == "v1":  # 지난주 로직: 손목 하강 또는 손목이 무릎 높이
            f = throwing | (lowreach > 0)
        else:
            with np.errstate(invalid="ignore"):
                low = ((tilt >= cfg.bend_tilt_deg) | (knee <= cfg.crouch_knee_deg)
                       | (hr <= cfg.crouch_height_ratio)) & (hg <= cfg.reach_low_ratio)
            placing = np.zeros_like(low)
            j = 0
            csum = np.concatenate([[0], np.cumsum(low)])
            for i in range(len(t)):
                while t[i] - t[j] > cfg.placing_window_sec:
                    j += 1
                n = i - j + 1
                if t[i] - t[j] >= cfg.placing_window_sec * 0.6 and n >= 2:
                    placing[i] = (csum[i + 1] - csum[j]) / n >= cfg.placing_min_frac
            f = throwing | placing.astype(bool)
        ft = t[f.astype(bool)]
        if mode != "v1" and len(ft):  # hold_sec 동안 유지
            ext = []
            for x in ft:
                ext.extend(t[(t >= x) & (t <= x + cfg.hold_sec)])
            ft = np.unique(ext)
        fired.append(ft)
    return np.unique(np.concatenate(fired)) if fired else np.array([])


def score_clip(ft, intervals, dur):
    hit = any(((ft >= s - HIT_MARGIN) & (ft <= e + HIT_MARGIN)).any() for s, e in intervals)
    first = None
    if hit:
        s0 = intervals[0][0]
        cand = ft[(ft >= s0 - HIT_MARGIN)]
        first = float(cand[0] - s0) if len(cand) else None
    outside = ft[[all(not (s - FP_MARGIN <= x <= e + FP_MARGIN) for s, e in intervals) for x in ft]] if len(ft) else ft
    episodes = 0
    last = None
    for x in outside:
        if last is None or x - last > MERGE_GAP:
            episodes += 1
        last = x
    neg_min = max(dur - sum(e - s + 2 * FP_MARGIN for s, e in intervals), 1.0) / 60
    return hit, episodes, neg_min, first


def evaluate(data, cfg, names, mode="v2"):
    hits, eps, negm, lat, per, fired = 0, 0, 0.0, [], {}, 0
    for n in names:
        times, tracks, intervals = data[n]
        ft = fire_times(tracks, cfg, mode)
        fired += len(ft)
        h, e, nm, first = score_clip(ft, intervals, float(times[-1]) if len(times) else 0)
        hits += h
        eps += e
        negm += nm
        if first is not None:
            lat.append(first)
        per[n] = {"hit": bool(h), "fp_episodes": e, "first_fire_vs_label_sec": first}
    return {"clips": len(names), "recall": hits / max(len(names), 1), "fp_episodes": eps,
            "fp_per_min": eps / max(negm, 1e-6), "fired_frames": fired,
            "median_latency_sec": float(np.median(lat)) if lat else None,
            "per_clip": per}


def objective(r):
    # 탐지율 우선, 오탐 1회/분당 0.15 감점. 같으면 의심이 덜 켜지는(보수적인) 기준값 선호
    return (round(r["recall"] - 0.15 * r["fp_per_min"], 6), -r["fired_frames"])


GRID = {
    "bend_tilt_deg": [30, 35, 40, 45, 50, 60],
    "crouch_knee_deg": [90, 100, 110, 120, 130],
    "crouch_height_ratio": [0.6, 0.7, 0.75, 0.8, 0.85],
    "reach_low_ratio": [0.15, 0.2, 0.25, 0.3, 0.35, 0.4],
    "placing_min_frac": [0.4, 0.6, 0.8],
    "placing_window_sec": [0.4, 0.6, 1.0],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(ROOT / "datasets" / "aihub_dump"))
    ap.add_argument("--config", default=str(ROOT / "configs" / "action_config.json"))
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--write", action="store_true", help="튜닝 결과를 --config 경로에 저장")
    a = ap.parse_args()

    ds = Path(a.dataset)
    meta = json.loads((ds / "clips.json").read_text(encoding="utf-8"))
    base = ActionConfig.load(a.config)
    data = {}
    for n, m in meta.items():
        f = ds / "keypoints" / f"{n}.jsonl"
        if f.exists():
            times, tracks = load_features(f, base)
            data[n] = (times, tracks, m["drop_intervals"])
    if not data:
        sys.exit("keypoints 폴더에 추출 결과가 없습니다. extract_keypoints.py 를 먼저 실행하세요.")
    names = sorted(data)
    train = [n for n in names if n.startswith("155-")] or names
    valid = [n for n in names if n.startswith("157-")]
    print(f"클립 {len(names)}개 (튜닝용 {len(train)}, 검증용 {len(valid)})")

    report = {"v1_last_week": evaluate(data, base, names, "v1"), "v2_current": evaluate(data, base, names)}
    for k in ("v1_last_week", "v2_current"):
        r = report[k]
        print(f"{k:14s} 탐지율 {r['recall']:.0%}  오탐 {r['fp_episodes']}회 ({r['fp_per_min']:.2f}/분)")
    if not a.eval_only:
        best, best_cfg = None, None
        keys = list(GRID)
        for vals in itertools.product(*GRID.values()):
            cfg = replace(base, **dict(zip(keys, vals)))
            r = evaluate(data, cfg, train)
            if best is None or objective(r) > objective(best):
                best, best_cfg = r, cfg
        tuned = {k: getattr(best_cfg, k) for k in keys}
        report["tuned_params"] = tuned
        report["tuned_train"] = best
        report["tuned_valid"] = evaluate(data, best_cfg, valid) if valid else None
        report["tuned_all"] = evaluate(data, best_cfg, names)
        print("튜닝 결과:", tuned)
        for k in ("tuned_train", "tuned_valid", "tuned_all"):
            r = report[k]
            if r:
                print(f"{k:14s} 탐지율 {r['recall']:.0%}  오탐 {r['fp_episodes']}회 ({r['fp_per_min']:.2f}/분)"
                      f"  지연 중앙값 {r['median_latency_sec']}")
        if a.write:
            Path(a.config).parent.mkdir(parents=True, exist_ok=True)
            Path(a.config).write_text(json.dumps(best_cfg.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
            print("저장:", a.config)
    out = ds / "tuning_report.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print("리포트:", out)


if __name__ == "__main__":
    main()
