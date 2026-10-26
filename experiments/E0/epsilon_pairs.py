"""
File · experiments/E0/epsilon_pairs.py
Purpose · Measure ε over every twin pair a control or episode run recorded (METHOD.md §6: ε is measured on the exact image sent to the model and
reported as a distribution; METHOD.md §2: a replica is at pixel distance ≤ ε from the genuine prompt), and apply the pre-registered small-ε threshold of
(SSIM ≥ 0.95 and normalised L2 ≤ 0.05 on the prompt crop) so that every later pair can be reported as matched or not.
Description · Reads a run's episodes.jsonl, pairs each genuine episode with the replica episode of the same cell, act, agent and repetition, and
computes ε with src/awp/metrics.py on the prompt crop when the run recorded a prompt box, or on the whole screen when it did not (the chat cell, where
the genuine prompt is the client's own page and the replica is a post, so no common prompt region exists; those pairs are reported on the whole screen
and are expected to be unmatched, which is a stated property of that cell, not a defect). Also runs the per-pair check: the fraction of pixels that
differ outside the prompt region, which must be zero for a matched pair. Local-class run; reads images only.
Inputs/Outputs · In: results/E0/<run>/episodes.jsonl and shots/ for each run named on the command line. Out: results/E0/epsilon-pairs/pairs.json
(one row per pair), summary.json (distribution per cell, matched counts); SUMMARY on stdout.
Depends on · src/awp/metrics.py.
Invariant · Nothing is excluded: a pair whose screenshots differ in size or whose twin is missing is reported with its reason and counted as no_data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp import metrics

OUT = ROOT / "results" / "E0" / "epsilon-pairs"
RUNS = ["h0-browser-controls", "h0-chat-controls"]
KEY = ("cell", "act", "agent", "rep")


def pairs_of(run):
    d = ROOT / "results" / "E0" / run
    ep = d / "episodes.jsonl"
    if not ep.exists():
        return [{"run": run, "no_data": "no episodes.jsonl"}]
    rows = [json.loads(line) for line in ep.read_text(encoding="utf-8").splitlines() if line.strip()]
    index = {tuple(r[k] for k in KEY) + (r["condition"],): r for r in rows}
    out = []
    for key, g in sorted(index.items()):
        if key[-1] != "genuine":
            continue
        r = index.get(key[:-1] + ("replica",))
        base = dict(zip(KEY, key[:-1], strict=False), run=run)
        if r is None:
            out.append({**base, "no_data": "no replica twin"})
            continue
        gp, rp = d / "shots" / Path(g["shot"]).name, d / "shots" / Path(r["shot"]).name
        if not (gp.exists() and rp.exists()):
            out.append({**base, "no_data": "screenshot missing"})
            continue
        box = (g.get("prompt") or {}).get("box")
        whole = box is None
        if whole:
            box = [0, 0, metrics.to_gray(gp.read_bytes()).shape[1], metrics.to_gray(gp.read_bytes()).shape[0]]
        e = metrics.pair_epsilon(gp.read_bytes(), rp.read_bytes(), box, margin=0 if whole else 30)
        out.append({**base, **e, "region": "whole screen" if whole else "prompt crop", "genuine_shot": gp.name, "replica_shot": rp.name})
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [p for run in (sys.argv[1:] or RUNS) for p in pairs_of(run)]
    (OUT / "pairs.json").write_text(json.dumps(rows, indent=1, sort_keys=True), encoding="utf-8")
    summary = {}
    for cell in sorted({r.get("cell") for r in rows if r.get("cell")}):
        sel = [r for r in rows if r.get("cell") == cell and "l2" in r]
        nd = [r for r in rows if r.get("cell") == cell and "no_data" in r]
        summary[cell] = {
            **metrics.summarise_epsilon(sel),
            "region": sel[0]["region"] if sel else None,
            "no_data": len(nd),
            "outside_changed_max": max((r["outside_changed_fraction"] for r in sel if r.get("outside_changed_fraction") is not None), default=None),
        }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    print("SUMMARY " + json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
