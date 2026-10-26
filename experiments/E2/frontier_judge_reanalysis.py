"""
File · experiments/E2/frontier_judge_reanalysis.py
Purpose · Recompute the frontier judge's rates from the 272 replies already recorded, under the exact interval method of without sending a
single new request. The original run (E2/frontier-judge-on-pairs) cost 2.64 USD; its verdicts are a property of those replies and do not change when
the arithmetic applied to them changes, so re-querying the vendor to fix our own statistics would be waste.
Description · Reads the stored trials, counts REFUSE verdicts by cell and condition, drops replies that carry no verdict and reports how many, and
writes one summary per cell with Clopper-Pearson intervals on each rate, Newcombe's interval on the advantage and Fisher's exact two-sided test. The
advantage is the refusal rate on replicas minus the refusal rate on genuine prompts, so a defence that works is positive and this one is not.
Inputs/Outputs · In: results/E2/frontier-judge-on-pairs/trials.json. Out: results/E2/<AWP_RUN_NAME>/summary.json, and SUMMARY on stdout.
Depends on · src/awp/metrics.py.
Invariant · No network call; the input is read and never written; every rate carries its N and the count of replies that could not be parsed.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp import metrics

SRC = ROOT / "results" / "E2" / "frontier-judge-on-pairs" / "trials.json"
OUT = ROOT / "results" / "E2" / os.environ.get("AWP_RUN_NAME", "frontier-judge-exact")


def main():
    if not SRC.exists():
        print("SUMMARY " + json.dumps({"status": "no_trials", "looked_for": str(SRC.relative_to(ROOT))}))
        return 1
    trials = json.loads(SRC.read_text(encoding="utf-8"))
    by = defaultdict(lambda: {"genuine": [0, 0], "replica": [0, 0], "unparseable": 0})
    for t in trials:
        cell = t.get("cell")
        if t.get("verdict") not in ("REFUSE", "SAFE"):
            by[cell]["unparseable"] += 1
            continue
        arm = by[cell]["replica" if t.get("condition") == "replica" else "genuine"]
        arm[0] += 1
        arm[1] += 1 if t["verdict"] == "REFUSE" else 0
    cells = {}
    for cell, v in sorted(by.items()):
        ng, fg = v["genuine"]
        nr, fr = v["replica"]
        row = {
            "n_genuine": ng,
            "n_replica": nr,
            "unparseable": v["unparseable"],
            "refuse_rate_genuine": round(fg / ng, 4) if ng else None,
            "refuse_rate_replica": round(fr / nr, 4) if nr else None,
            "refuse_rate_genuine_ci95": metrics.clopper_pearson(fg, ng) if ng else None,
            "refuse_rate_replica_ci95": metrics.clopper_pearson(fr, nr) if nr else None,
            "note": "advantage is the refusal rate on replicas minus the rate on genuine prompts; a working defence is positive",
        }
        if ng and nr:
            row["defence_advantage"] = round(fr / nr - fg / ng, 4)
            row["defence_advantage_ci95"] = metrics.newcombe_difference(fr, nr, fg, ng)
            row["exact_p"] = metrics.fisher_exact_two_sided(fr, nr - fr, fg, ng - fg)
        cells[cell] = row
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {
        "cells": cells,
        "source": {"run": "E2/frontier-judge-on-pairs", "trials": len(trials)},
        "method": "recomputed from stored replies under ; no request was sent",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    print("SUMMARY " + json.dumps({"status": "done", "cells": len(cells), "trials": len(trials)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
