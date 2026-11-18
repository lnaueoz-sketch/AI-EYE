"""서버 코드 점검: 실제 모델 + 새 행동 인식 로직으로 클립 하나를 처리해 본다.

사용: python scripts/smoke_test.py
결과: 점검결과/smoke_result.txt, 점검결과/annotated_*.jpg
"""
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "점검결과"
OUT.mkdir(exist_ok=True)
log = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    log.append(s)


try:
    import cv2

    from app.ai.models import YoloModels
    from app.ai.pipeline import StreamProcessor
    from app.ai.pose_features import ActionConfig
    from app.ai.visualize import draw
    from app.config import settings

    cfg = ActionConfig.load(settings.action_config_path)
    say("기준값 파일:", settings.action_config_path, "있음" if Path(settings.action_config_path).exists() else "없음(기본값)")
    say("기준값:", json.dumps(cfg.to_dict(), ensure_ascii=False))
    models = YoloModels(settings.detect_model_path, settings.pose_model_path, settings.device,
                        settings.imgsz, settings.detect_conf, settings.pose_conf)
    say("모델 로드 OK, 클래스:", models.names)

    meta = json.loads((ROOT / "datasets/aihub_dump/clips.json").read_text(encoding="utf-8"))
    name = "155-4_cam01_dump01_place04_day_spring"
    m = meta[name]
    cap = cv2.VideoCapture(str(ROOT / "datasets/aihub_dump" / m["clip"]))
    fps = cap.get(cv2.CAP_PROP_FPS) or 10
    sp = StreamProcessor(models, settings.keypoint_conf, cfg)
    s, e = m["drop_intervals"][0]
    actions, fired, idx, saved, t0 = {}, [], -1, 0, time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        t = idx / fps
        r = sp.process(frame, t)
        for p in r.persons:
            actions[p.action] = actions.get(p.action, 0) + 1
        if any(p.suspect_motion for p in r.persons):
            fired.append(round(t, 1))
            if saved < 2 and s <= t <= e:
                cv2.imwrite(str(OUT / f"annotated_{saved + 1}.jpg"), draw(frame, r, settings.keypoint_conf))
                saved += 1
        d = r.to_dict()
        assert "action" in d["persons"][0] if d["persons"] else True
    say(f"처리 {idx + 1}프레임, {time.time() - t0:.1f}초")
    say("행동 분포:", actions)
    say(f"정답 투기 구간: {s}~{e}초")
    inside = [x for x in fired if s - 1 <= x <= e + 1]
    say("의심 행동 켜진 시각(정답 구간 안):", inside[:10], "..." if len(inside) > 10 else "")
    say("결과:", "성공 - 투기 구간에서 의심 행동 감지" if inside else "투기 구간에서 감지 못함")

    from app.main import app  # 서버 앱 import 확인
    say("서버 앱 import OK:", app.title, app.version)
    say("SMOKE TEST PASSED")
except Exception:
    say("SMOKE TEST FAILED")
    say(traceback.format_exc())
finally:
    (OUT / "smoke_result.txt").write_text("\n".join(log), encoding="utf-8")
