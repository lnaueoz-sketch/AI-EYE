"""평가용 클립에서 관절·객체 탐지 결과를 한 번만 뽑아 저장 (11월 2주차 행동 인식 튜닝용)

모델 추론은 오래 걸리므로 여기서 한 번만 하고, 기준값 튜닝(scripts/tune_actions.py)은
저장된 결과만으로 빠르게 반복한다.

사용:  python scripts/extract_keypoints.py --dataset datasets/aihub_dump
결과:  datasets/aihub_dump/keypoints/<클립이름>.jsonl  (한 줄 = 한 프레임)
       {"t": 1.2, "poses": [{"bbox":[x1,y1,x2,y2], "score":0.9, "kp":[[x,y,conf]*17]}],
        "dets": [["trash_bag", 0.81, x1,y1,x2,y2], ...]}
이미 끝난 클립은 건너뛰므로 중간에 꺼도 다시 실행하면 이어서 진행한다.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai.models import YoloModels  # noqa: E402
from app.config import settings  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(ROOT / "datasets" / "aihub_dump"))
    ap.add_argument("--stride", type=int, default=1, help="N프레임마다 1번 (클립은 10fps)")
    ap.add_argument("--imgsz", type=int, default=settings.imgsz)
    ap.add_argument("--limit", type=int, default=0, help="앞에서부터 N개 클립만")
    a = ap.parse_args()

    ds = Path(a.dataset)
    meta = json.loads((ds / "clips.json").read_text(encoding="utf-8"))
    out_dir = ds / "keypoints"
    out_dir.mkdir(exist_ok=True)
    names = list(meta)[: a.limit or None]
    todo = [n for n in names if not (out_dir / f"{n}.jsonl").exists()]
    print(f"클립 {len(names)}개 중 {len(names) - len(todo)}개 완료, {len(todo)}개 남음")
    if not todo:
        return

    models = YoloModels(settings.detect_model_path, settings.pose_model_path, settings.device,
                        a.imgsz, settings.detect_conf, 0.25)  # 포즈는 낮은 신뢰도까지 저장, 튜닝에서 거름
    models.warmup()
    started, done_frames = time.time(), 0
    for ci, name in enumerate(todo, 1):
        m = meta[name]
        cap = cv2.VideoCapture(str(ds / m["clip"]))
        fps = cap.get(cv2.CAP_PROP_FPS) or m.get("fps", 10)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        tmp = out_dir / f"{name}.jsonl.partial"
        idx = -1
        with open(tmp, "w", encoding="utf-8") as f:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                idx += 1
                if idx % a.stride:
                    continue
                poses = models.pose(frame)
                dets = models.detect(frame)
                f.write(json.dumps({
                    "t": round(idx / fps, 3),
                    "poses": [{"bbox": [round(v, 1) for v in p.bbox], "score": round(p.score, 3),
                               "kp": [[round(float(x), 1), round(float(y), 1), round(float(c), 3)]
                                      for (x, y), c in zip(p.keypoints, p.keypoint_conf)]} for p in poses],
                    "dets": [[d.label, round(d.confidence, 3)] + [round(v, 1) for v in d.bbox] for d in dets],
                }) + "\n")
                done_frames += 1
                if idx % 100 == 0:
                    el = time.time() - started
                    print(f"  [{ci}/{len(todo)}] {name}  {idx}/{total}프레임  ({done_frames / max(el, 1e-6):.1f} fps)",
                          flush=True)
        cap.release()
        tmp.replace(out_dir / f"{name}.jsonl")
        el = time.time() - started
        left = (len(todo) - ci) * el / ci
        print(f"완료 {ci}/{len(todo)}: {name}  (경과 {el / 60:.1f}분, 남은 시간 약 {left / 60:.0f}분)", flush=True)
    print("모든 클립 추출 완료")


if __name__ == "__main__":
    main()
