"""
File · experiments/E0/bench_cpu_inference.py
Purpose · E0 step 1 engineering (in-guest CPU realisation; maintainer ruling of 2026-10-19): measure what one agent step costs on this guest's CPU for each pinned open vision model, so the VM size request and the choice of model size rest on numbers, not estimates.
Description · For each model configuration present under ../alpha-vendor/models (pinned revisions, sha256-verified manifest), runs llama-mtmd-cli from the Kali llama.cpp package on one 1280x800 screenshot cropped from a pinned WAInjectBench benign page, with a computer-use style prompt, 64 output tokens, temperature 0, all cores. Three repetitions per configuration. Parses llama.cpp's own perf lines (load, image encode, prompt eval, eval) and samples the child's peak resident memory from /proc. A configuration whose files are absent is reported as not_present, never skipped silently. Local-class run; no network.
Inputs/Outputs · In: ../alpha-vendor/models/<dir>/*.gguf, ../alpha-vendor/WAInjectBench/data/image/benign/screenshot/2.png, /usr/bin/llama-mtmd-cli. Out: results/E0/bench-cpu-inference/bench.json, results/E0/bench-cpu-inference/shot-1280x800.png, per-run logs; SUMMARY on stdout.
Depends on · src/awp/proc.py, llama.cpp-tools (Kali), ImageMagick convert.
Invariant · Nothing under ../alpha-vendor is written; every child dies with this script; the screenshot is derived from pinned data by a fixed crop.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp.proc import Child

VENDOR = ROOT.parent / "alpha-vendor"
MODELS = VENDOR / "models"
OUT = ROOT / "results" / "E0" / "bench-cpu-inference"
SHOT_SRC = VENDOR / "WAInjectBench" / "data" / "image" / "benign" / "screenshot" / "2.png"
CONFIGS = [
    {
        "name": "qwen3-vl-8b-q8_0",
        "model": MODELS / "qwen3-vl-8b-instruct-gguf" / "Qwen3VL-8B-Instruct-Q8_0.gguf",
        "mmproj": MODELS / "qwen3-vl-8b-instruct-gguf" / "mmproj-Qwen3VL-8B-Instruct-F16.gguf",
    },
    {
        "name": "qwen3-vl-32b-q8_0",
        "model": MODELS / "qwen3-vl-32b-instruct-gguf" / "Qwen3VL-32B-Instruct-Q8_0.gguf",
        "mmproj": MODELS / "qwen3-vl-32b-instruct-gguf" / "mmproj-Qwen3VL-32B-Instruct-F16.gguf",
    },
]
PROMPT = (
    "You are operating a desktop computer. The image is the current screen. Task: open the inbox. "
    'Reply with exactly one action as JSON, either {"action": "click", "x": <int>, "y": <int>} or {"action": "type", "text": "<str>"}.'
)
N_PREDICT = 64
REPS = 3
THREADS = os.cpu_count() or 1
DEADLINE_S = 2400

PERF = {
    "load_ms": re.compile(r"load time\s*=\s*([\d.]+) ms"),
    "prompt_eval": re.compile(r"prompt eval time\s*=\s*([\d.]+) ms\s*/\s*(\d+) tokens.*?([\d.]+) tokens per second"),
    "eval": re.compile(r"\beval time\s*=\s*([\d.]+) ms\s*/\s*(\d+) runs.*?([\d.]+) tokens per second"),
    "image_encode_ms": re.compile(r"image.*?encoded in\s*([\d.]+) ms", re.IGNORECASE),
}


def make_shot():
    OUT.mkdir(parents=True, exist_ok=True)
    shot = OUT / "shot-1280x800.png"
    if not shot.exists():
        subprocess.run(["convert", str(SHOT_SRC), "-crop", "1280x800+0+0", "+repage", str(shot)], check=True, timeout=120)
    return shot


def peak_rss_gb(pid):
    try:
        for line in (Path("/proc") / str(pid) / "status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) / 1e6
    except OSError:
        pass
    return None


def run_once(cfg, shot, rep):
    log = OUT / f"{cfg['name']}-rep{rep}.log"
    cmd = [
        "llama-mtmd-cli",
        "-m",
        str(cfg["model"]),
        "--mmproj",
        str(cfg["mmproj"]),
        "--image",
        str(shot),
        "-p",
        PROMPT,
        "-n",
        str(N_PREDICT),
        "--temp",
        "0",
        "-t",
        str(THREADS),
        "-tb",
        str(THREADS),
        "-c",
        "4096",
        "-ngl",
        "0",
    ]
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as fh:
        child = Child(cmd, DEADLINE_S, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT)
        peak = 0.0
        while child.proc.poll() is None:
            r = peak_rss_gb(child.proc.pid)
            peak = max(peak, r or 0.0)
            time.sleep(0.5)
        rc = child.proc.returncode
    wall = time.time() - t0
    text = log.read_text(encoding="utf-8", errors="replace")
    rec = {"rep": rep, "exit": rc, "timed_out": child.timed_out, "wall_s": round(wall, 1), "peak_rss_gb": round(peak, 2), "threads": THREADS}
    m = PERF["load_ms"].search(text)
    rec["load_ms"] = float(m.group(1)) if m else None
    m = PERF["prompt_eval"].search(text)
    rec["prompt_tokens"], rec["prefill_tok_s"], rec["prefill_ms"] = (int(m.group(2)), float(m.group(3)), float(m.group(1))) if m else (None, None, None)
    m = PERF["eval"].search(text)
    rec["gen_tokens"], rec["decode_tok_s"], rec["decode_ms"] = (int(m.group(2)), float(m.group(3)), float(m.group(1))) if m else (None, None, None)
    enc = PERF["image_encode_ms"].findall(text)
    rec["image_encode_ms"] = sum(float(x) for x in enc) if enc else None
    tail = [
        l
        for l in text.splitlines()
        if l.strip()
        and not l.startswith(
            ("llama", "load", "print_info", "ggml", "clip", "mtmd", "common", "main", "system", "sampler", "generate", "encoding", "image", "decoding", "srv")
        )
    ]
    rec["reply_excerpt"] = " ".join(tail[-3:])[:300]
    if rec["prefill_ms"] is not None and rec["decode_ms"] is not None:
        rec["step_s"] = round(((rec["image_encode_ms"] or 0.0) + rec["prefill_ms"] + rec["decode_ms"]) / 1000, 1)
    else:
        rec["step_s"] = None
    return rec


def summarize(runs):
    ok = [r for r in runs if r["step_s"] is not None]
    if not ok:
        return {"n_ok": 0}
    med = lambda k: round(statistics.median(r[k] for r in ok if r[k] is not None), 2)
    return {
        "n_ok": len(ok),
        "prompt_tokens": ok[0]["prompt_tokens"],
        "prefill_tok_s_median": med("prefill_tok_s"),
        "decode_tok_s_median": med("decode_tok_s"),
        "image_encode_s_median": round(med("image_encode_ms") / 1000, 1) if ok[0]["image_encode_ms"] is not None else None,
        "step_s_median": med("step_s"),
        "step_s_min_max": [min(r["step_s"] for r in ok), max(r["step_s"] for r in ok)],
        "peak_rss_gb_max": max(r["peak_rss_gb"] for r in ok),
        "load_s_median": round(med("load_ms") / 1000, 1) if ok[0]["load_ms"] is not None else None,
    }


def main():
    shot = make_shot()
    out = {"threads": THREADS, "n_predict": N_PREDICT, "reps": REPS, "shot": str(shot.relative_to(ROOT)), "configs": {}}
    for cfg in CONFIGS:
        if not (cfg["model"].exists() and cfg["mmproj"].exists()):
            out["configs"][cfg["name"]] = {"status": "not_present"}
            continue
        runs = [run_once(cfg, shot, i + 1) for i in range(REPS)]
        out["configs"][cfg["name"]] = {"status": "ran", "model_bytes": cfg["model"].stat().st_size, "runs": runs, "summary": summarize(runs)}
        (OUT / "bench.json").write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    (OUT / "bench.json").write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print("SUMMARY " + json.dumps({k: (v.get("summary") or v.get("status")) for k, v in out["configs"].items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
