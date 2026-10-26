"""
File · experiments/E0/classifier_probe.py
Purpose · C-0027 records that every request the vendor's classifier halted was a replica and that all of them fall in one condition, the structured
observation at the framed level, while the provenance observation was never halted although it carries the same tree. Those two requests differ in two
ways at once: each node carries a principal annotation, and the task carries a policy sentence. This probe separates them, so the pattern can be
reported with a cause rather than with a shrug.
Description · One screenshot, recorded by an acting episode at the framed level on the replica half, is replayed under four conditions in a two by two:
the tree with or without its principal annotations, crossed with the task with or without the policy sentence. The annotated tree is the one the
provenance arm recorded; the plain tree is that same string with the annotations removed, so the only difference between the two is the annotation
itself and not the node order, the boxes or the frame headers. One request per trial, no retries, the first reply read and the trial ended, so the
spend equals the number of trials. What is recorded is the stop reason: a halt arrives as a refusal with no content and is the vendor's decision, not
the model's.
Inputs/Outputs · In: results/E1/paired/episodes.jsonl for the screenshot and the two trees, src/awp/policy.py for the sentence, configs/pins.yaml for
the pinned model and prices, ANTHROPIC_API_KEY placed in the environment by ./lab run. Out: results/E0/<AWP_RUN_NAME>/trials.json and summary.json.
Depends on · src/awp/frontier.py (AnthropicAgent), src/awp/policy.py, the anthropic SDK pinned in pins.yaml.
Invariant · The key is read from the environment and never printed; one request per trial and no retries, so the spend equals the count; the four
conditions share one screenshot and one base task, so the only things that vary are the two factors named.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp import policy
from awp.frontier import AnthropicAgent

OUT = ROOT / "results" / "E0" / os.environ.get("AWP_RUN_NAME", "classifier-probe")
K = int(os.environ.get("AWP_K") or 10)


def pinned_frontier():
    line = next((x for x in (ROOT / "configs" / "pins.yaml").read_text(encoding="utf-8").splitlines() if x.strip().startswith("anthropic_frontier:")), None)
    if line is None:
        raise RuntimeError("pins.yaml has no models.anthropic_frontier entry")
    mid = re.search(r"pinned_id:\s*([A-Za-z0-9._-]+)", line)
    inp = re.search(r"price_usd_per_mtok:\s*\{[^}]*?input:\s*([0-9.]+)", line)
    outp = re.search(r"price_usd_per_mtok:\s*\{[^}]*?output:\s*([0-9.]+)", line)
    frac = re.search(r"cache_read_fraction_of_input:\s*([0-9.]+)", line)
    return mid.group(1), {"input": float(inp.group(1)), "output": float(outp.group(1)), "cache_read_fraction_of_input": float(frac.group(1)) if frac else 0.05}


def source():
    """One framed replica episode from the provenance arm: its screenshot, its annotated tree and its task."""
    rows = [json.loads(line) for line in (ROOT / "results/E1/paired/episodes.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in rows:
        if (
            r.get("agent") == "anthropic_frontier"
            and r.get("observation") == "provenance"
            and r.get("cell") == "browser-l2"
            and r.get("condition") == "replica"
            and r.get("structure")
            and (r.get("steps") or [])
            and r["steps"][0].get("shot")
        ):
            shot = ROOT / "results/E1/paired/shots" / os.path.basename(r["steps"][0]["shot"])
            if shot.exists():
                return r, shot
    return None, None


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("SUMMARY " + json.dumps({"status": "no_key"}))
        return 1
    ep, shot = source()
    if ep is None:
        print("SUMMARY " + json.dumps({"status": "no_source_episode"}))
        return 1
    annotated = ep["structure"]
    plain = re.sub(r" principal=\w+", "", annotated)
    if plain == annotated:
        print("SUMMARY " + json.dumps({"status": "source_tree_carries_no_annotation"}))
        return 1
    base_task = ep["task"].replace(policy.POLICY_TEXT, "").strip()
    with_policy = base_task + " " + policy.POLICY_TEXT.strip()
    conditions = {
        "tree_plain__task_plain": (plain, base_task),
        "tree_annotated__task_plain": (annotated, base_task),
        "tree_plain__task_policy": (plain, with_policy),
        "tree_annotated__task_policy": (annotated, with_policy),
    }
    model, price = pinned_frontier()
    cap = float(os.environ.get("AWP_MAX_USD", "0") or 0) or None
    agent = AnthropicAgent("anthropic_frontier", model, 1280, 832, max_tokens=int(os.environ.get("AWP_MAX_TOKENS", "256")))
    png = shot.read_bytes()
    OUT.mkdir(parents=True, exist_ok=True)
    trials = []
    for rep in range(1, K + 1):
        for name, (tree, task) in conditions.items():
            if cap and agent.spend_usd(price) >= cap:
                print(f"stopped at the declared cap: {agent.spend_usd(price):.3f} of {cap:.2f}", flush=True)
                break
            agent.reset(task, session=f"probe-{rep}-{abs(hash(name)) % 100000}")
            action = agent.step(png, 1, structure=tree)
            t = (agent.timings or [{}])[-1]
            trials.append(
                {
                    "condition": name,
                    "tree": "annotated" if tree is annotated else "plain",
                    "task": "policy" if task is with_policy else "plain",
                    "rep": rep,
                    "stop_reason": t.get("stop_reason"),
                    "halted": t.get("stop_reason") == "refusal",
                    "action": (action.get("type") if isinstance(action, dict) else None),
                }
            )
            print(f"[{len(trials)}] {name} rep{rep}: stop={t.get('stop_reason')}", flush=True)
    cells = {}
    for name in conditions:
        sel = [t for t in trials if t["condition"] == name]
        cells[name] = {"n": len(sel), "halted": sum(1 for t in sel if t["halted"]), "stop_reasons": dict(Counter(t["stop_reason"] for t in sel))}
    usd = agent.spend_usd(price)
    (OUT / "trials.json").write_text(json.dumps(trials, indent=1, sort_keys=True), encoding="utf-8")
    (OUT / "summary.json").write_text(
        json.dumps(
            {"cells": cells, "source_episode": {"cell": ep["cell"], "act": ep["act"], "context": ep.get("context"), "shot": shot.name}, "model": model, "k": K},
            indent=1,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (ROOT / "results" / "E0" / f"{os.environ.get('AWP_RUN_NAME', 'classifier-probe')}.usage.json").write_text(
        json.dumps({"usd_spent": usd, **agent.usage, "price_usd_per_mtok": price}, indent=1, sort_keys=True), encoding="utf-8"
    )
    print("SUMMARY " + json.dumps({"status": "done", "cells": cells, "usd": round(usd, 4)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
