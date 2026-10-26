"""
File · experiments/E2/screener_on_pairs.py
Purpose · E2, C-0012 (METHOD.md §5 H2, §7 E2): run the pixel-side screener we reproduced in E0 over our own twin pairs and measure its defence
advantage, the rate at which it flags a replica minus the rate at which it flags the genuine prompt. The screener is the strongest published setting
of its class and its own published numbers were re-measured first (C-0001), as the method requires.
Description · Reads a run's episode records, pairs each genuine episode with the replica episode of the same cell, act, agent and repetition, and
stages the two screenshots into the directory layout the archived runner walks: the replica is the positive class (the detector should flag it) and the
genuine prompt is the negative class (it should not). One category per cell, so each cell gets its own rate. The archived runner is invoked exactly as
it was for C-0001, single-threaded OCR, and its own jsonl output is parsed for the detected ids. The defence advantage per cell is the flag rate on
replicas minus the flag rate on genuine prompts, with a cluster bootstrap over pairs; at a cell whose twins are bit-identical the advantage is zero by
construction, which is reported as such and not as an empirical finding. Local-class run; no model, no network.
Inputs/Outputs · In: results/E0/<run>/episodes.jsonl and shots/ (default the recorded control runs), the archived SnapGuard at the pinned hash, the
SnapGuard virtualenv. Out: results/E2/screener-on-pairs/raw/<cell>/ (the runner's own output), pairs.json, summary.json; SUMMARY on stdout.
Depends on · src/awp/proc.py, src/awp/metrics.py, ../alpha-vendor/snapguard/src (pins.yaml defences.snapguard), .venv-snapguard.
Invariant · The staged images are symlinks; nothing under the clone or the run directories is written; a pair whose screenshot is missing is reported
as no_data and never dropped; the detector's settings are those of C-0001 and are recorded with the result.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp import metrics
from awp.proc import Child

VENDOR = ROOT.parent / "alpha-vendor"
RUNNER = VENDOR / "snapguard" / "src"
VENV = ROOT / ".venv-snapguard" / "bin" / "python"
OUT = ROOT / "results" / "E2" / os.environ.get("AWP_RUN_NAME", "screener-on-pairs")
RUNS = ["h0-browser-controls", "h0-chat-controls"]
KEY = ("cell", "act", "agent", "rep")
DEADLINE_S = 7200


def pairs_from(run):
    """Pairs of a run's record; `run` is a name under results/E0 or an exp/name path such as E1/paired, whose episodes carry context and observation."""
    d = ROOT / "results" / run if "/" in run else ROOT / "results" / "E0" / run
    ep = d / "episodes.jsonl"
    if not ep.exists():
        return []
    rows = [json.loads(line) for line in ep.read_text(encoding="utf-8").splitlines() if line.strip()]
    index = {tuple(r.get(k) for k in KEY) + (r.get("context"), r.get("observation"), r["condition"]): r for r in rows}
    out = []
    for key, g in sorted(index.items(), key=str):
        if key[-1] != "genuine":
            continue
        r = index.get(key[:-1] + ("replica",))
        base = dict(zip(KEY, key[: len(KEY)], strict=False), context=key[-3], observation=key[-2], run=run)
        if r is None:
            out.append({**base, "no_data": "no replica twin"})
            continue
        gshot = g.get("shot") or (g.get("steps") or [{}])[0].get("shot")
        rshot = r.get("shot") or (r.get("steps") or [{}])[0].get("shot")
        if not gshot or not rshot:
            out.append({**base, "no_data": "no first observation recorded"})
            continue
        gp, rp = d / "shots" / Path(gshot).name, d / "shots" / Path(rshot).name
        if not (gp.exists() and rp.exists()):
            out.append({**base, "no_data": "screenshot missing"})
            continue
        out.append({**base, "genuine": gp, "replica": rp, "prompt_box": (g.get("prompt") or {}).get("box")})
    return out


def stage(pairs, staging):
    """The archived runner walks data_dir/{benign,malicious}/<category>/<id>.png; the replica is the positive class, the genuine prompt the negative."""
    index = {}
    for cell in sorted({p["cell"] for p in pairs if "no_data" not in p}):
        for label, which in (("malicious", "replica"), ("benign", "genuine")):
            d = staging / cell / label / cell
            d.mkdir(parents=True, exist_ok=True)
            for i, p in enumerate([q for q in pairs if q.get("cell") == cell and "no_data" not in q], start=1):
                os.symlink(p[which], d / f"{i}.png")
                index.setdefault((cell, label), {})[i] = p
    return index


def run_cell(cell, staging, results_dir):
    res = results_dir / cell
    res.mkdir(parents=True, exist_ok=True)
    for f in ("snapguard.jsonl", "snapguard_debug.jsonl"):
        (res / f).write_text("", encoding="utf-8")
    log = open(res / "run.log", "w", encoding="utf-8")  # noqa: SIM115  held for the child's lifetime
    # WHY: the settings of C-0001, single-threaded OCR, so the number here is comparable with the reproduction
    env = dict(os.environ, OMP_NUM_THREADS="1", OMP_THREAD_LIMIT="1", MKL_NUM_THREADS="1", TOKENIZERS_PARALLELISM="false")
    child = Child(
        [str(VENV), "main_image_split.py", "--data_dir", str(staging / cell), "--detector", "snapguard", "--result_dir", str(res), "--gpu", ""],
        DEADLINE_S,
        cwd=str(RUNNER),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    rc = child.proc.wait()
    log.close()
    return {"exit": rc, "timed_out": child.timed_out, "dir": str(res.relative_to(ROOT))}


def detections(results_dir, cell):
    out = {}
    p = results_dir / cell / "snapguard.jsonl"
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["label"]] = {"detected": sorted(int(i) for i in row["detect_ids"]), "total": row["total_num"]}
    return out


def main():
    if not VENV.exists() or not RUNNER.exists():
        print("SUMMARY " + json.dumps({"status": "screener_absent", "venv": VENV.exists(), "runner": RUNNER.exists()}))
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    raw = OUT / "raw"
    raw.mkdir(exist_ok=True)
    pairs = [p for run in (sys.argv[1:] or RUNS) for p in pairs_from(run)]
    usable = [p for p in pairs if "no_data" not in p]
    if not usable:
        print("SUMMARY " + json.dumps({"status": "no_pairs", "no_data": len(pairs)}))
        return 1
    staging = Path(tempfile.mkdtemp(prefix="awp-screener-pairs-"))
    stage(usable, staging)
    t0 = time.time()
    status, rows = {}, []
    for cell in sorted({p["cell"] for p in usable}):
        status[cell] = run_cell(cell, staging, raw)
        det = detections(raw, cell)
        flagged = {"replica": set(det.get("malicious", {}).get("detected", [])), "genuine": set(det.get("benign", {}).get("detected", []))}
        members = [q for q in usable if q["cell"] == cell]
        for i, p in enumerate(members, start=1):
            rows.append(
                {
                    "cell": cell,
                    "act": p["act"],
                    "agent": p["agent"],
                    "rep": p["rep"],
                    "run": p["run"],
                    "flagged_replica": i in flagged["replica"],
                    "flagged_genuine": i in flagged["genuine"],
                    "genuine_shot": p["genuine"].name,
                    "replica_shot": p["replica"].name,
                }
            )
        (OUT / "pairs.json").write_text(json.dumps(rows, indent=1, sort_keys=True), encoding="utf-8")
    summary = {"status": status, "no_data": [p for p in pairs if "no_data" in p], "wall_s": round(time.time() - t0, 1), "cells": {}}
    for cell in sorted({r["cell"] for r in rows}):
        sel = [r for r in rows if r["cell"] == cell]
        as_rows = [{"y": 1 if r["flagged_replica"] else 0, "condition": "replica", "context": f"{r['act']}-{r['rep']}"} for r in sel]
        as_rows += [{"y": 1 if r["flagged_genuine"] else 0, "condition": "genuine", "context": f"{r['act']}-{r['rep']}"} for r in sel]
        stats = metrics.u_cr_d(as_rows)
        summary["cells"][cell] = {
            "n_pairs": len(sel),
            "flag_rate_replica": round(sum(1 for r in sel if r["flagged_replica"]) / len(sel), 4),
            "flag_rate_genuine": round(sum(1 for r in sel if r["flagged_genuine"]) / len(sel), 4),
            "defence_advantage": None if stats["D"] is None else round(-stats["D"], 4),
            "defence_advantage_ci95": [round(-v, 4) for v in reversed(stats.get("D_ci95") or [])] or None,
            "note": "the advantage is the flag rate on replicas minus the flag rate on genuine prompts; where the twins are bit-identical it is zero by construction",
        }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    print("SUMMARY " + json.dumps({k: v for k, v in summary.items() if k != "status"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
