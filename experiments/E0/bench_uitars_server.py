"""
File · experiments/E0/bench_uitars_server.py
Purpose · Measure one agent step for UI-TARS-1.5-7B on the native llama.cpp build after its conversion (2026-10-19), with the same method, screenshot and prompt as experiments/E0/bench_cpu_server.py, whose configuration list is immutable once run (check artifact_freshness), so this is a thin wrapper with its own configuration list.
Description · Imports the measurement functions of bench_cpu_server and runs two configurations: UI-TARS Q8_0 (requantised from F16) with its F16 projector on the native build, and the same on the Kali package build for comparison. Three requests each, timings from the server's own fields. Local-class run; loopback only.
Inputs/Outputs · In: ../alpha-vendor/models/ui-tars-1.5-7b-gguf, the two llama-server binaries. Out: results/E0/bench-uitars-server/bench.json and server logs; SUMMARY on stdout.
Depends on · experiments/E0/bench_cpu_server.py, src/awp/proc.py.
Invariant · Same prompt, screenshot, token cap and temperature as bench_cpu_server; nothing under ../alpha-vendor is written.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_cpu_server as B

OUT = Path(__file__).resolve().parents[2] / "results" / "E0" / "bench-uitars-server"
CONFIGS = [("native-build", "ui-tars-1.5-7b-q8_0", None), ("kali-package", "ui-tars-1.5-7b-q8_0", None)]


def main():
    B.OUT = OUT
    OUT.mkdir(parents=True, exist_ok=True)
    shot = B.make_shot()
    out = {"threads": B.THREADS, "n_predict": B.N_PREDICT, "reps": B.REPS, "shot": str(shot.relative_to(B.ROOT)), "configs": {}}
    for build, weights_name, image_max_tokens in CONFIGS:
        name, rec = B.run_config(build, weights_name, image_max_tokens, shot)
        out["configs"][name] = rec
        (OUT / "bench.json").write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print("SUMMARY " + json.dumps({k: (v.get("summary") or v.get("status")) for k, v in out["configs"].items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
