#!/usr/bin/env python3
"""Generate a reference still on the GPU host with local MiniMax H3.

This machine currently has H3 *video* weights, not a separate H3-Image checkpoint.
The script queues a short silent Ref2VA clip (4–5 s) and extracts stills.
Run it on the GPU host, never via an assistant image generator.

Usage:
  python3 refs/bin/gen_still.py --id c-peilaojian --prompt refs/jobs/c-peilaojian.txt
  python3 refs/bin/gen_still.py --id c-huoshuan --prompt refs/jobs/c-huoshuan.txt \\
      --ref refs/v2/s-bengzhan.jpg --ref refs/v2/c-guchen.jpg

Stills land in refs/pending/<id>_t*.jpg and a contact sheet.
Approved stills should be copied into refs/vN/ by hand after review.
"""
from __future__ import annotations

from pathlib import Path
import argparse, json, os, shutil, subprocess, sys, time, uuid, urllib.request, urllib.error

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
ROOT = None  # set in main

# 24 fps frame grid: max(5, round(a*24)) + (5 - (max(5, round(a*24)) % 17)) % 17
def frame_count(seconds: float) -> int:
    n = max(5, int(round(seconds * 24)))
    return n + (5 - (n % 17)) % 17


def http_json(path, data=None, method=None, timeout=60):
    url = COMFY + path
    if data is None:
        req = urllib.request.Request(url, method=method or "GET")
    else:
        raw = json.dumps(data).encode()
        req = urllib.request.Request(url, data=raw, method=method or "POST",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def queue_busy() -> bool:
    try:
        q = http_json("/queue")
        running = q.get("queue_running") or []
        pending = q.get("queue_pending") or []
        return bool(running or pending)
    except Exception as e:
        print(f"cannot read ComfyUI queue: {e}", file=sys.stderr)
        sys.exit(2)


def load_workflow(path):
    with open(path) as f:
        return json.load(f)


def upload_image(path: str) -> str:
    import mimetypes
    boundary = uuid.uuid4().hex
    name = os.path.basename(path)
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + f.read() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        COMFY + "/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        out = json.loads(resp.read().decode())
    return out.get("name") or name


def build_graph(template, prompt, width, height, duration, seed, tag, refs):
    g = json.loads(json.dumps(template))  # deep copy
    g.pop("115", None)
    for k in list(g):
        if k in ("114", "115b", "115c", "115d") or str(k).startswith("refimg"):
            g.pop(k, None)
    node_ids = ["114", "115b", "115c", "115d"]
    used = []
    for i, fn in enumerate(refs):
        nid = node_ids[i]
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": fn}}
        used.append(nid)
    r = g["105:104"]["inputs"]
    for k in list(r):
        if k.startswith("ref_images."):
            r.pop(k)
    r["prompt"] = prompt
    r["width"] = width
    r["height"] = height
    for i, nid in enumerate(used):
        r[f"ref_images.ref_image_{i}"] = [nid, 0]
    g["105:111"]["inputs"]["value"] = float(duration)
    g["105:126"]["inputs"]["value"] = True  # turbo
    g["105:15"]["inputs"]["noise_seed"] = int(seed)
    g["92"]["inputs"]["filename_prefix"] = f"video/fanzimu_still_{tag}"
    return g


def wait_output(prompt_id, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            hist = http_json(f"/history/{prompt_id}", timeout=30)
        except Exception:
            time.sleep(5)
            continue
        item = hist.get(prompt_id) if isinstance(hist, dict) else None
        if item and item.get("outputs"):
            return item
        if item and item.get("status", {}).get("status_str") == "error":
            raise RuntimeError(json.dumps(item.get("status"), ensure_ascii=False)[:2000])
        time.sleep(5)
    raise TimeoutError(f"timed out waiting for {prompt_id}")


def find_mp4(item, tag):
    outputs = item.get("outputs") or {}
    for node in outputs.values():
        for key in ("gifs", "videos", "images"):
            for ent in node.get(key) or []:
                fn = ent.get("filename")
                sub = ent.get("subfolder") or ""
                if fn and fn.endswith(".mp4"):
                    # typical: output/video/...
                    return fn, sub
    # fallback by prefix
    import glob
    pats = [
        f"/root/local/minimaxH3/ComfyUI/output/video/fanzimu_still_{tag}*.mp4",
        f"/root/fanzi-mu/renders/stills/fanzimu_still_{tag}*.mp4",
    ]
    hits = []
    for p in pats:
        hits.extend(glob.glob(p))
    if hits:
        hits.sort(key=os.path.getmtime, reverse=True)
        return hits[0], None
    raise FileNotFoundError(f"no mp4 for {tag}")


def extract_stills(mp4, dest_dir, stem, times):
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for t in times:
        out = dest_dir / f"{stem}_t{t:.1f}.jpg".replace("t0.0", "t0.0")
        # normalize 1.0 -> t1.0
        out = dest_dir / f"{stem}_t{t:g}.jpg"
        cmd = [
            "ffmpeg", "-y", "-ss", str(t), "-i", mp4,
            "-frames:v", "1", "-q:v", "2", str(out),
        ]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        paths.append(out)
    sheet = dest_dir / f"{stem}_sheet.jpg"
    if paths:
        subprocess.check_call(
            ["ffmpeg", "-y", "-i", str(paths[0] if len(paths) == 1 else paths[0])]
            + sum([["-i", str(p)] for p in paths[1:]], [])
            + ["-filter_complex", f"hstack=inputs={len(paths)}", str(sheet)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ) if len(paths) > 1 else shutil.copy(paths[0], sheet)
    return paths, sheet


def main():
    global ROOT
    here = Path(__file__).resolve()
    ROOT = here.parents[2]  # .../fanzi-mu
    ap = argparse.ArgumentParser(description="Generate a reference still on the GPU host")
    ap.add_argument("--id", required=True, help="asset id, e.g. c-peilaojian")
    ap.add_argument("--prompt", required=True, help="path to the six-section prompt file")
    ap.add_argument("--ref", action="append", default=[], help="optional local ref image (repeat, max 4)")
    ap.add_argument("--seed", type=int, default=2026111801)
    ap.add_argument("--duration", type=float, default=5.0)
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--workflow", default=str(ROOT / "workflows/ref2va_verified.json"))
    ap.add_argument("--force", action="store_true", help="queue even if ComfyUI already has a job")
    args = ap.parse_args()

    if not (0 < len(args.ref) <= 4 or len(args.ref) == 0):
        sys.exit("at most 4 --ref images")
    if not os.path.isfile(args.prompt):
        sys.exit(f"missing prompt: {args.prompt}")
    if not os.path.isfile(args.workflow):
        sys.exit(f"missing workflow: {args.workflow}")

    if not args.force and queue_busy():
        sys.exit("ComfyUI already has a job in the queue. Wait, or pass --force.")

    prompt = Path(args.prompt).read_text(encoding="utf-8")
    uploaded = []
    for p in args.ref:
        if not os.path.isfile(p):
            sys.exit(f"missing ref: {p}")
        uploaded.append(upload_image(p))
        print(f"uploaded {p} -> {uploaded[-1]}")

    tag = args.id.replace("/", "_")
    template = load_workflow(args.workflow)
    graph = build_graph(template, prompt, args.width, args.height, args.duration, args.seed, tag, uploaded)

    out_dir = ROOT / "renders" / "stills"
    out_dir.mkdir(parents=True, exist_ok=True)
    wf_path = out_dir / f"{tag}_workflow_api.json"
    wf_path.write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")

    res = http_json("/prompt", {"prompt": graph, "client_id": str(uuid.uuid4())})
    prompt_id = res.get("prompt_id")
    print(f"queued {args.id} prompt_id={prompt_id} seed={args.seed}")
    item = wait_output(prompt_id)
    fn, sub = find_mp4(item, tag)
    if os.path.isabs(str(fn)):
        mp4 = str(fn)
    else:
        base = "/root/local/minimaxH3/ComfyUI/output"
        mp4 = os.path.join(base, sub or "", fn) if sub is not None else os.path.join(base, "video", fn)
        if not os.path.isfile(mp4):
            # second try
            alt = os.path.join(base, sub or "video", fn)
            if os.path.isfile(alt):
                mp4 = alt
    if not os.path.isfile(mp4):
        raise FileNotFoundError(f"mp4 not on disk: {fn} sub={sub}")

    dest = out_dir / f"{tag}.mp4"
    shutil.copy2(mp4, dest)
    times = [0.4, 2.0, 4.0] if args.duration >= 4 else [0.2]
    stills, sheet = extract_stills(dest, ROOT / "refs" / "pending", args.id, times)
    print("mp4:", dest)
    for p in stills:
        print("still:", p)
    print("sheet:", sheet)
    print("review these, then copy the keeper to refs/vN/")


if __name__ == "__main__":
    # Path imported for type, fix later
    main()
