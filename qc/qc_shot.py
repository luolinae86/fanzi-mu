#!/usr/bin/env python3
"""Run H3 shot QC on the GPU host (CPU only). Do not use the GPU."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("OMP_NUM_THREADS", "4")

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ALNUM_RE = re.compile(r"[A-Za-z0-9]{2,}")
FN_RE = re.compile(r"(?P<shot>sh\d+[a-z]?)_p\d+t\d+(?P<ver>v\d+)", re.I)


def h3_frames(seconds: float, fps: int = 24) -> int:
    base = max(5, int(round(seconds * fps)))
    return base + (5 - (base % 17)) % 17


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def ffprobe(video: Path) -> dict:
    cp = run([
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-print_format", "json", str(video),
    ])
    data = json.loads(cp.stdout)
    vs = next(s for s in data["streams"] if s.get("codec_type") == "video")
    aus = [s for s in data["streams"] if s.get("codec_type") == "audio"]
    rate = vs.get("r_frame_rate") or vs.get("avg_frame_rate") or "24/1"
    if "/" in str(rate):
        a, b = str(rate).split("/")
        fps = float(a) / float(b or 1)
    else:
        fps = float(rate)
    duration = float(vs.get("duration") or data["format"].get("duration") or 0)
    return {
        "width": int(vs["width"]),
        "height": int(vs["height"]),
        "fps": fps,
        "duration_s": duration,
        "has_audio": bool(aus),
        "audio_codec": aus[0].get("codec_name") if aus else None,
        "nb_frames": int(vs["nb_frames"]) if vs.get("nb_frames") not in (None, "N/A") else None,
    }


def peak_db(video: Path) -> float | None:
    cp = run([
        "ffmpeg", "-hide_banner", "-i", str(video),
        "-af", "volumedetect", "-f", "null", "-",
    ], check=False)
    text = (cp.stderr or "") + (cp.stdout or "")
    m = re.search(r"max_volume:\s*([-\d.]+)\s*dB", text)
    return float(m.group(1)) if m else None


def extract_frames(video: Path, out_dir: Path, duration_s: float) -> list[tuple[int, Path]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[int, Path]] = []
    n = max(1, int(math.floor(duration_s)) + (1 if duration_s % 1 >= 0.25 else 0))
    if duration_s < 1:
        n = 1
    for t in range(n):
        dest = out_dir / f"t{t:02d}.jpg"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", str(t), "-i", str(video),
            "-frames:v", "1", "-q:v", "2", "-y", str(dest),
        ])
        if dest.exists() and dest.stat().st_size > 0:
            frames.append((t, dest))
    return frames


def contact_sheet(frames: list[tuple[int, Path]], dest: Path, flags: dict[int, list[str]]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    if not frames:
        return
    ims = [(t, Image.open(p).convert("RGB")) for t, p in frames]
    w, h = ims[0][1].size
    thumb_w = 240
    thumb_h = int(h * thumb_w / w)
    cols = min(4, len(ims))
    rows = math.ceil(len(ims) / cols)
    pad, label_h = 8, 28
    sheet = Image.new("RGB", (cols * (thumb_w + pad) + pad, rows * (thumb_h + label_h + pad) + pad), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    for i, (t, im) in enumerate(ims):
        r, c = divmod(i, cols)
        x = pad + c * (thumb_w + pad)
        y = pad + r * (thumb_h + label_h + pad)
        thumb = im.resize((thumb_w, thumb_h))
        issues = flags.get(t) or []
        if issues:
            border = Image.new("RGB", (thumb_w + 6, thumb_h + 6), (200, 40, 40))
            sheet.paste(border, (x - 3, y - 3))
        sheet.paste(thumb, (x, y))
        tag = f"t={t}s" + (f"  !{len(issues)}" if issues else "")
        draw.text((x, y + thumb_h + 4), tag, fill=(255, 80, 80) if issues else (220, 220, 220), font=font)
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, quality=90)


def load_expect(shot: str, board_path: Path | None, exp_path: Path) -> dict:
    data = json.loads(exp_path.read_text()) if exp_path.exists() else {"defaults": {}, "shots": {}}
    expect = dict(data.get("defaults") or {})
    expect.update((data.get("shots") or {}).get(shot) or {})
    if board_path and board_path.exists():
        board = json.loads(board_path.read_text())
        rec = next((s for s in board.get("shots") or [] if s.get("id") == shot), None)
        if rec:
            expect.setdefault("duration_s", rec.get("duration_s"))
            dlg = rec.get("dialogue") or []
            if dlg and all("画外音" in (d.get("who") or "") for d in dlg):
                expect.setdefault("mouths_closed", True)
            refs = [r for r in (rec.get("refs") or []) if str(r).startswith("c-")]
            if "persons_max" not in expect and refs:
                extra = 1 if "砖头" in (rec.get("action") or "") else 0
                expect["persons_max"] = len(refs) + extra
            if "persons_min" not in expect:
                size = (rec.get("shot_size") or "").lower()
                expect["persons_min"] = 0 if "insert" in size or "high-angle" in size else 1
    expect.setdefault("width", 720)
    expect.setdefault("height", 1280)
    expect.setdefault("fps", 24)
    expect.setdefault("has_audio", True)
    expect.setdefault("duration_tol_s", 1.5)
    expect.setdefault("forbid_text", True)
    expect.setdefault("text_conf_min", 0.62)
    expect.setdefault("person_score_min", 0.42)
    expect.setdefault("jaw_open_min", 0.35)
    expect.setdefault("mouths_closed", False)
    if "hands_max" not in expect and expect.get("persons_max") is not None:
        expect["hands_max"] = 2 * int(expect["persons_max"])
    return expect


def parse_shot(video: Path, shot: str | None) -> tuple[str, str | None]:
    if shot:
        m = FN_RE.search(video.name)
        return shot, (m.group("ver") if m else None)
    m = FN_RE.search(video.name)
    if not m:
        raise SystemExit(f"cannot infer shot id from filename: {video.name}")
    return m.group("shot"), m.group("ver")


class Detectors:
    def __init__(self, models: Path, person_score_min: float):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            FaceLandmarker,
            FaceLandmarkerOptions,
            HandLandmarker,
            HandLandmarkerOptions,
            ObjectDetector,
            ObjectDetectorOptions,
            RunningMode,
        )

        self.mp = mp
        self.person = ObjectDetector.create_from_options(ObjectDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(models / "efficientdet_lite2.tflite")),
            running_mode=RunningMode.IMAGE,
            score_threshold=person_score_min,
            max_results=10,
            category_allowlist=["person"],
        ))
        self.hands = HandLandmarker.create_from_options(HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(models / "hand_landmarker.task")),
            running_mode=RunningMode.IMAGE,
            num_hands=6,
            min_hand_detection_confidence=0.4,
        ))
        self.faces = FaceLandmarker.create_from_options(FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(models / "face_landmarker.task")),
            running_mode=RunningMode.IMAGE,
            num_faces=4,
            min_face_detection_confidence=0.4,
            output_face_blendshapes=True,
        ))
        from rapidocr_onnxruntime import RapidOCR
        self.ocr = RapidOCR()

    def _image(self, bgr):
        import numpy as np
        rgb = bgr[:, :, ::-1].copy()
        return self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)

    def inspect(self, bgr, expect: dict) -> dict:
        img = self._image(bgr)
        persons = []
        for det in (self.person.detect(img).detections or []):
            cats = det.categories or []
            if not cats:
                continue
            name = (cats[0].category_name or "").lower()
            score = float(cats[0].score or 0)
            if name == "person":
                box = det.bounding_box
                persons.append({"score": round(score, 3), "x": box.origin_x, "y": box.origin_y,
                                "w": box.width, "h": box.height})
        hand_res = self.hands.detect(img)
        n_hands = len(hand_res.hand_landmarks or [])
        face_res = self.faces.detect(img)
        mouths = []
        for i, blends in enumerate(face_res.face_blendshapes or []):
            scores = {b.category_name: float(b.score) for b in blends}
            jaw = scores.get("jawOpen", 0.0)
            mouths.append({"jawOpen": round(jaw, 3), "open": jaw >= float(expect["jaw_open_min"])})
        texts = []
        if expect.get("forbid_text"):
            ocr_out, _ = self.ocr(bgr)
            for item in ocr_out or []:
                # item: [box, text, conf]
                if not item or len(item) < 3:
                    continue
                text = str(item[1]).strip()
                try:
                    conf = float(item[2])
                except (TypeError, ValueError):
                    continue
                if conf < float(expect["text_conf_min"]):
                    continue
                if not (CJK_RE.search(text) or ALNUM_RE.search(text)):
                    continue
                if len(text) < 2 and not CJK_RE.search(text):
                    continue
                texts.append({"text": text, "conf": round(conf, 3)})
        return {"persons": persons, "n_persons": len(persons), "n_hands": n_hands,
                "mouths": mouths, "texts": texts}


def evaluate(per_frame: list[dict], expect: dict, probe: dict) -> tuple[str, list[dict], dict[int, list[str]]]:
    issues: list[dict] = []
    flags: dict[int, list[str]] = {}

    def add(t, code, msg):
        issues.append({"t": t, "code": code, "msg": msg})
        flags.setdefault(t if t is not None else -1, []).append(code)

    if probe["width"] != expect["width"] or probe["height"] != expect["height"]:
        add(None, "spec_size", f"画幅 {probe['width']}x{probe['height']}，期望 {expect['width']}x{expect['height']}")
    if abs(probe["fps"] - expect["fps"]) > 0.15:
        add(None, "spec_fps", f"帧率 {probe['fps']:.3f}，期望 {expect['fps']}")
    if expect.get("has_audio") and not probe["has_audio"]:
        add(None, "spec_audio", "没有音轨")
    dur_exp = expect.get("duration_s")
    if dur_exp:
        expected_len = h3_frames(float(dur_exp), int(expect["fps"])) / float(expect["fps"])
        if abs(probe["duration_s"] - expected_len) > float(expect["duration_tol_s"]):
            add(None, "spec_duration", f"时长 {probe['duration_s']:.2f}s，期望约 {expected_len:.2f}s")

    pmin = expect.get("persons_min")
    pmax = expect.get("persons_max")
    hmax = expect.get("hands_max")
    for fr in per_frame:
        t = fr["t"]
        n = fr["n_persons"]
        if pmin is not None and n < int(pmin):
            add(t, "persons_low", f"t={t}s 检出 {n} 人，期望至少 {pmin}")
        if pmax is not None and n > int(pmax):
            add(t, "persons_high", f"t={t}s 检出 {n} 人，期望最多 {pmax}")
        if hmax is not None and fr["n_hands"] > int(hmax):
            add(t, "hands_high", f"t={t}s 检出 {fr['n_hands']} 只手，期望最多 {hmax}")
        if n >= 1 and fr["n_hands"] > 2 * max(n, 1):
            add(t, "hands_vs_people", f"t={t}s {n} 人却有 {fr['n_hands']} 只手")
        if expect.get("mouths_closed"):
            opened = [m for m in fr["mouths"] if m.get("open")]
            if opened:
                add(t, "mouth_open", f"t={t}s 有 {len(opened)} 张嘴张开（jawOpen {[m['jawOpen'] for m in opened]}），此镜应闭嘴")
        if fr["texts"]:
            shown = "、".join(x["text"] for x in fr["texts"][:6])
            add(t, "fake_text", f"t={t}s 画面疑似有字：{shown}")

    hard = {i["code"] for i in issues}
    if hard & {"persons_high", "persons_low", "hands_high", "hands_vs_people", "mouth_open", "spec_size", "spec_fps", "spec_audio"}:
        verdict = "FAIL"
    elif hard:
        verdict = "WARN"
    else:
        verdict = "PASS"
    return verdict, issues, flags


def write_md(path: Path, shot: str, ver: str | None, verdict: str, probe: dict, expect: dict, issues: list[dict], peak: float | None) -> None:
    lines = [
        f"# {shot} {ver or ''} 质检报告".replace("  ", " "),
        f"",
        f"结论：**{verdict}**",
        f"",
        f"- 规格：{probe['width']}x{probe['height']}  {probe['fps']:.3f}fps  {probe['duration_s']:.2f}s  {'有音轨' if probe['has_audio'] else '无音轨'}",
        f"- 峰值音量：{peak} dB" if peak is not None else "- 峰值音量：未测",
        f"- 期望人数：{expect.get('persons_min')}–{expect.get('persons_max')}；最多手数：{expect.get('hands_max')}；闭嘴：{bool(expect.get('mouths_closed'))}；禁字：{bool(expect.get('forbid_text'))}",
        f"",
        f"## 问题" if issues else "## 问题",
    ]
    if issues:
        for i in issues:
            t = "规格" if i["t"] is None else f"t={i['t']}s"
            lines.append(f"- [{i['code']}] {t} {i['msg']}")
    else:
        lines.append("- 无自动检出问题")
    lines.append("")
    lines.append("自动检测只覆盖人数、手数、张嘴和画面假字。口型是否合拍、角色像不像、镜头感觉仍需看完整视频。")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="H3 shot QC on GPU host, CPU only")
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--shot")
    ap.add_argument("--board", type=Path, default=Path("/root/fanzi-mu/ep01-script-board.json"))
    ap.add_argument("--expect", type=Path, default=root / "expectations.json")
    ap.add_argument("--models", type=Path, default=root / "models")
    ap.add_argument("--outdir", type=Path)
    args = ap.parse_args()
    video = args.video.resolve()
    if not video.exists():
        raise SystemExit(f"video not found: {video}")
    shot, ver = parse_shot(video, args.shot)
    outdir = args.outdir or video.parent / f"{shot}_{ver or 'v'}_qc"
    outdir = outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    expect = load_expect(shot, args.board if args.board.exists() else None, args.expect)
    probe = ffprobe(video)
    peak = peak_db(video)
    frames = extract_frames(video, outdir / "frames", probe["duration_s"])

    import cv2
    det = Detectors(args.models, float(expect["person_score_min"]))
    per_frame = []
    for t, path in frames:
        bgr = cv2.imread(str(path))
        if bgr is None:
            continue
        rec = det.inspect(bgr, expect)
        rec["t"] = t
        rec["file"] = str(path)
        per_frame.append(rec)

    verdict, issues, flags = evaluate(per_frame, expect, probe)
    sheet = outdir / "contact_sheet.jpg"
    contact_sheet(frames, sheet, flags)
    report = {
        "shot": shot,
        "version": ver,
        "video": str(video),
        "verdict": verdict,
        "probe": probe,
        "peak_db": peak,
        "expect": expect,
        "frames": per_frame,
        "issues": issues,
        "contact_sheet": str(sheet),
    }
    (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(outdir / "report.md", shot, ver, verdict, probe, expect, issues, peak)
    print(json.dumps({"verdict": verdict, "shot": shot, "version": ver, "outdir": str(outdir),
                      "n_issues": len(issues), "report": str(outdir / "report.md")}, ensure_ascii=False, indent=2))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
