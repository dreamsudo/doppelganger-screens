"""
File · experiments/E0/bench_cpu_server.py
Purpose · E0 step 1 engineering: measure one agent step against llama-server, the realisation the harness will use, for each open-model configuration, each llama.cpp build, and the two levers that can cut the image cost (an 8-bit projector; a cap on image tokens), reading the server's own timing fields instead of parsing a CLI log (the CLI of attempt 1, printed no perf lines).
Description · For each configuration (binary, model, projector) that is present: start llama-server on the loopback address, wait for /health, send the same 1280x800 screenshot (cropped from a pinned benign page) with a computer-use prompt three times through /v1/chat/completions, 64 output tokens, temperature 0, a per-request nonce in the system message so the server's prefix cache cannot reuse the previous request, and record prompt tokens, prompt processing time (which includes the image encode), generation time and rate, wall time per request, the reply, and the server's peak resident memory from /proc. Absent configurations are reported as not_present. Local-class run; loopback only; no network beyond 127.0.0.1.
Inputs/Outputs · In: ../alpha-vendor/models/<dir>/*.gguf, /usr/bin/llama-server (Kali package) and ../alpha-vendor/llama.cpp-src/build/bin/llama-server (native build from the Kali source), the pinned screenshot. Out: results/E0/bench-cpu-server/bench.json, per-config server logs; SUMMARY on stdout.
Depends on · src/awp/proc.py, llama.cpp 1:0.5.0 (package and native build), ImageMagick convert.
Invariant · Nothing under ../alpha-vendor is written; every server dies with this script; the listener binds 127.0.0.1 only.
"""

from __future__ import annotations

import base64
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp.proc import Child

VENDOR = ROOT.parent / "alpha-vendor"
MODELS = VENDOR / "models"
OUT = ROOT / "results" / "E0" / "bench-cpu-server"
SHOT_SRC = VENDOR / "WAInjectBench" / "data" / "image" / "benign" / "screenshot" / "2.png"
BINS = {"kali-package": Path("/usr/bin/llama-server"), "native-build": VENDOR / "llama.cpp-src" / "build" / "bin" / "llama-server"}
WEIGHTS = {
    "qwen3-vl-8b-q8_0": (
        MODELS / "qwen3-vl-8b-instruct-gguf" / "Qwen3VL-8B-Instruct-Q8_0.gguf",
        MODELS / "qwen3-vl-8b-instruct-gguf" / "mmproj-Qwen3VL-8B-Instruct-F16.gguf",
    ),
    "qwen3-vl-8b-q8_0+mmproj-q8_0": (
        MODELS / "qwen3-vl-8b-instruct-gguf" / "Qwen3VL-8B-Instruct-Q8_0.gguf",
        MODELS / "qwen3-vl-8b-instruct-gguf" / "mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf",
    ),
    "ui-tars-1.5-7b-q8_0": (MODELS / "ui-tars-1.5-7b-gguf" / "UI-TARS-1.5-7B-Q8_0.gguf", MODELS / "ui-tars-1.5-7b-gguf" / "mmproj-UI-TARS-1.5-7B-F16.gguf"),
}
# (build, weights, image_max_tokens or None). The 32B is not re-measured: attempt 1 showed it takes the whole guest at 8-bit.
CONFIGS = [
    ("kali-package", "qwen3-vl-8b-q8_0", None),
    ("native-build", "qwen3-vl-8b-q8_0", None),
    ("kali-package", "qwen3-vl-8b-q8_0", 512),
    ("kali-package", "qwen3-vl-8b-q8_0+mmproj-q8_0", None),
    ("kali-package", "ui-tars-1.5-7b-q8_0", None),
]
PROMPT = (
    "You are operating a desktop computer. The image is the current screen. Task: open the inbox. "
    'Reply with exactly one action as JSON, either {"action": "click", "x": <int>, "y": <int>} or {"action": "type", "text": "<str>"}.'
)
PORT = 18080
N_PREDICT = 64
REPS = 3
THREADS = os.cpu_count() or 1
SERVER_DEADLINE_S = 3600
REQUEST_TIMEOUT_S = 1800


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


def scrub(path):
    """Rewrite absolute home paths echoed by the server to tree-relative ones (check secrets_and_identifiers)."""
    t = path.read_text(encoding="utf-8", errors="replace")
    home = str(Path.home())
    t = t.replace(str(ROOT.parent), "..").replace(home, "~")
    path.write_text(t, encoding="utf-8")


def version_of(binary):
    try:
        r = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=60, check=False)
        return (r.stdout + r.stderr).strip().splitlines()[-1][:200]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def wait_health(deadline_s, child):
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        if child.proc.poll() is not None:
            return False, "server exited during load"
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5) as r:
                if r.status == 200:
                    return True, round(time.time() - t0, 1)
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1)
    return False, "health timeout"


def request(shot_b64, nonce):
    body = {
        "model": "bench",
        "temperature": 0,
        "max_tokens": N_PREDICT,
        "messages": [
            {"role": "system", "content": f"Session {nonce}."},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{shot_b64}"}}, {"type": "text", "text": PROMPT}]},
        ],
    }
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
        data = json.load(r)
    wall = time.time() - t0
    t = data.get("timings") or {}
    reply = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    return {
        "wall_s": round(wall, 1),
        "prompt_tokens": t.get("prompt_n"),
        "prompt_ms": t.get("prompt_ms"),
        "prompt_tok_s": t.get("prompt_per_second"),
        "gen_tokens": t.get("predicted_n"),
        "gen_ms": t.get("predicted_ms"),
        "gen_tok_s": t.get("predicted_per_second"),
        "usage": data.get("usage"),
        "reply": reply[:300],
    }


def run_config(build, weights_name, image_max_tokens, shot):
    binary = BINS[build]
    model, mmproj = WEIGHTS[weights_name]
    name = f"{build}--{weights_name}" + (f"--imgmax{image_max_tokens}" if image_max_tokens else "")
    if not (binary.exists() and model.exists() and mmproj.exists()):
        return name, {"status": "not_present", "missing": [str(p) for p in (binary, model, mmproj) if not p.exists()]}
    log = open(OUT / f"{name}.server.log", "w", encoding="utf-8")  # noqa: SIM115  kept open for the server's lifetime
    cmd = [
        str(binary),
        "-m",
        str(model),
        "--mmproj",
        str(mmproj),
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "-t",
        str(THREADS),
        "-tb",
        str(THREADS),
        "-c",
        "4096",
        "-np",
        "1",
        "-ngl",
        "0",
    ]
    cmd += ["--image-max-tokens", str(image_max_tokens)] if image_max_tokens else ["--image-min-tokens", "1024"]
    child = Child(cmd, SERVER_DEADLINE_S, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT)
    rec = {
        "status": "ran",
        "binary": str(binary),
        "binary_version": version_of(binary),
        "model_bytes": model.stat().st_size,
        "mmproj": mmproj.name,
        "image_max_tokens": image_max_tokens,
        "threads": THREADS,
        "runs": [],
    }
    try:
        ok, info = wait_health(1800, child)
        rec["load_s" if ok else "load_error"] = info
        if ok:
            shot_b64 = base64.b64encode(shot.read_bytes()).decode()
            peak = 0.0
            for i in range(REPS):
                try:
                    r = request(shot_b64, nonce=f"{name}-{i + 1}-{int(time.time())}")
                except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
                    r = {"error": str(e)[:300]}
                r["rep"] = i + 1
                p = peak_rss_gb(child.proc.pid)
                peak = max(peak, p or 0.0)
                r["peak_rss_gb_so_far"] = round(peak, 2)
                if r.get("prompt_ms") is not None and r.get("gen_ms") is not None:
                    r["step_s"] = round((r["prompt_ms"] + r["gen_ms"]) / 1000, 1)
                rec["runs"].append(r)
            rec["peak_rss_gb"] = round(peak, 2)
    finally:
        child.stop()
        log.close()
        scrub(OUT / f"{name}.server.log")
    ok_runs = [r for r in rec["runs"] if r.get("step_s") is not None]
    if ok_runs:
        med = lambda k: round(statistics.median(r[k] for r in ok_runs), 2)
        rec["summary"] = {
            "n_ok": len(ok_runs),
            "prompt_tokens": ok_runs[0]["prompt_tokens"],
            "prompt_tok_s_median": med("prompt_tok_s"),
            "gen_tok_s_median": med("gen_tok_s"),
            "step_s_median": med("step_s"),
            "step_s_min_max": [min(r["step_s"] for r in ok_runs), max(r["step_s"] for r in ok_runs)],
            "wall_s_median": med("wall_s"),
            "peak_rss_gb": rec.get("peak_rss_gb"),
            "load_s": rec.get("load_s"),
        }
    else:
        rec["summary"] = {"n_ok": 0}
    return name, rec


def main():
    shot = make_shot()
    out = {"threads": THREADS, "n_predict": N_PREDICT, "reps": REPS, "shot": str(shot.relative_to(ROOT)), "configs": {}}
    for build, weights_name, image_max_tokens in CONFIGS:
        name, rec = run_config(build, weights_name, image_max_tokens, shot)
        out["configs"][name] = rec
        (OUT / "bench.json").write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print("SUMMARY " + json.dumps({k: (v.get("summary") or v.get("status")) for k, v in out["configs"].items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
