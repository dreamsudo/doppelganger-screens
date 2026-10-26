"""
File · experiments/E0/utility_floor_frontier.py
Purpose · E0, C-0018 for the frontier reference sample (METHOD.md §7 E0 "every agent's utility on every cell without any prompt, U ≥ U₀ required";
): the frontier model's utility on the instrumented cells, genuine condition only, so the paired runs know where it can be measured.
Description · The same episode loop as the open floor (src/awp/harness.py) driven by the frontier adapter in src/awp/agents.py, which speaks the
vendor's computer-use path exactly as measured in E0 (one toolset entry, screenshot in, tool call out). One frozen context (the first of the
two), k from configs/prereg.yaml `k_runs_frontier`, pixels-only observation. Refusals are counted as missing data and reported beside every number
. Spend is tracked from the vendor's reported usage against the pinned prices and the run stops before the next episode if the declared
cap would be exceeded, so the cap is honoured by construction and not by hope. Model class: runs only under ./lab run --class model with --max-usd.
Inputs/Outputs · In: ANTHROPIC_API_KEY in the environment (placed by ./lab run), configs/pins.yaml for the pinned model and prices, the lab
application and chat server. Out: results/E0/utility-floor-frontier/episodes.jsonl, shots/, summary.json, and
results/E0/utility-floor-frontier.usage.json for provenance; SUMMARY on stdout.
Depends on · src/awp/harness.py, src/awp/frontier.py (AnthropicAgent), src/awp/labapp.py, src/awp/chat.py, src/awp/browser.py, the anthropic SDK.
Invariant · The key is read from the environment only and never printed; spend is computed from reported usage and written before exit even on
failure; no episode starts once the projected spend would pass the cap; a refusal is recorded as a refusal.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp import labapp
from awp.browser import Browser
from awp.chat import ChatLab
from awp.frontier import AnthropicAgent
from awp.harness import Lab, archive_previous_shots, run_episode, run_episode_chat

RUN_NAME = os.environ.get("AWP_RUN_NAME", "utility-floor-frontier")  # ./lab run names the artifacts after the run
OUT = ROOT / "results" / "E0" / RUN_NAME
USAGE = ROOT / "results" / "E0" / f"{RUN_NAME}.usage.json"
ONLY_CELLS = [c for c in os.environ.get("AWP_CELLS", "").split(",") if c]  # a completion run for the cells a crash cost
ONLY_ACTS = [a for a in os.environ.get("AWP_ACTS", "").split(",") if a]  # likewise for the acts a cap cost
PER_EPISODE_USD_GUESS_CHAT = 0.45  # Measured: a chat credential episode of six to ten steps costs about 0.4 USD
PORT_A, PORT_B = 8441, 8442
CELLS = {
    "browser-l1": ("inline", ("CRED", "PERM", "CONF", "UPDT")),
    "browser-l2": ("iframe", ("CRED", "PERM", "CONF", "UPDT")),
    "chat-l1-web": (None, ("CRED", "PERM", "CONF")),
}
PER_EPISODE_USD_GUESS = 0.20  # a conservative per-episode allowance used only to decide whether the next episode may start under the cap


def pinned_frontier():
    line = next((x for x in (ROOT / "configs" / "pins.yaml").read_text(encoding="utf-8").splitlines() if x.strip().startswith("anthropic_frontier:")), None)
    if line is None:
        raise RuntimeError("pins.yaml has no models.anthropic_frontier entry")
    mid = re.search(r"pinned_id:\s*([A-Za-z0-9._-]+)", line)
    inp = re.search(r"price_usd_per_mtok:\s*\{[^}]*?input:\s*([0-9.]+)", line)
    outp = re.search(r"price_usd_per_mtok:\s*\{[^}]*?output:\s*([0-9.]+)", line)
    frac = re.search(r"cache_read_fraction_of_input:\s*([0-9.]+)", line)
    if not (mid and inp and outp):
        raise RuntimeError(f"could not read the pinned model id and prices from: {line[:160]}")
    return mid.group(1), {"input": float(inp.group(1)), "output": float(outp.group(1)), "cache_read_fraction_of_input": float(frac.group(1)) if frac else 0.05}


def write_usage(agent, price, note=None):
    usd = agent.spend_usd(price)
    USAGE.write_text(json.dumps({"usd_spent": usd, **agent.usage, "price_usd_per_mtok": price, "note": note}, indent=1, sort_keys=True), encoding="utf-8")
    return usd


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("SUMMARY " + json.dumps({"status": "no_key_in_environment"}))
        return 1
    cap = float(os.environ.get("AWP_MAX_USD", "0") or 0) or None
    prereg = yaml.safe_load((ROOT / "configs" / "prereg.yaml").read_text(encoding="utf-8"))
    contexts = yaml.safe_load((ROOT / "configs" / "contexts.yaml").read_text(encoding="utf-8"))["frozen"]
    ctx = contexts[0]  # the frontier sample uses the first frozen context
    u0, k = float(prereg["utility_floor"]), int(prereg["k_runs_frontier"])
    model, price = pinned_frontier()
    OUT.mkdir(parents=True, exist_ok=True)
    shots = OUT / "shots"
    shots.mkdir(exist_ok=True)
    archive_previous_shots(shots)
    events = OUT / "events.jsonl"
    events.write_text("", encoding="utf-8")
    servers, _ = labapp.serve(PORT_A, PORT_B, str(events))
    lab = Lab(PORT_A, PORT_B)
    chat = ChatLab(str(OUT / "events-chat.jsonl"))
    browser = Browser(deadline_s=14400)
    agent = AnthropicAgent("anthropic_frontier", model, browser.width, browser.height)
    rows, stopped = [], None
    try:
        with open(OUT / "episodes.jsonl", "w", encoding="utf-8") as fh:
            for cell, (level, acts) in CELLS.items():
                if ONLY_CELLS and cell not in ONLY_CELLS:
                    continue
                for act in acts:
                    if ONLY_ACTS and act not in ONLY_ACTS:
                        continue
                    for rep in range(1, k + 1):
                        spent = agent.spend_usd(price)
                        guess = PER_EPISODE_USD_GUESS_CHAT if cell.startswith("chat") else PER_EPISODE_USD_GUESS
                        if cap is not None and spent + guess > cap:
                            stopped = f"cap: {spent:.4f} USD spent, next episode could pass {cap} USD"
                            break
                        t0 = time.time()
                        if cell.startswith("chat"):
                            row = run_episode_chat(browser, chat, lab.control, lab.b, agent, act, "genuine", rep, shots, tag="uff-", context=ctx)
                        else:
                            row = run_episode(browser, lab, agent, cell, level, act, "genuine", rep, shots, tag="uff-", context=ctx)
                        row["usd_so_far"] = agent.spend_usd(price)
                        row["refusals_so_far"] = agent.usage["refusals"]
                        rows.append(row)
                        fh.write(json.dumps(row, sort_keys=True) + "\n")
                        fh.flush()
                        write_usage(agent, price, note="in progress")
                        print(
                            f"{cell} {act} rep{rep}: y={row['y']} {row['stop']} {row['n_steps']} steps {round(time.time() - t0)}s usd={row['usd_so_far']:.4f}",
                            flush=True,
                        )
                    if stopped:
                        break
                if stopped:
                    break
    finally:
        browser.close()
        chat.stop()
        for s in servers:
            s.shutdown()
        usd = write_usage(agent, price, note=stopped or "complete")
    summary = {"model": model, "context": ctx["id"], "k": k, "u0": u0, "usd_spent": usd, "stopped": stopped, "cells": {}}
    for cell, (_, acts) in CELLS.items():
        for act in acts:
            sel = [r for r in rows if r["cell"] == cell and r["act"] == act]
            if not sel:
                continue
            refused = [r for r in sel if r["stop"] == "refusal"]
            usable = [r for r in sel if r["stop"] != "refusal"]
            U = round(sum(r["y"] for r in usable) / len(usable), 4) if usable else None
            summary["cells"][f"{cell}/{act}"] = {"n": len(sel), "refusals": len(refused), "U": U, "measurable": None if U is None else U >= u0}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    print("SUMMARY " + json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
