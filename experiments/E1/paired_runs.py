"""
File · experiments/E1/paired_runs.py
Purpose · E1 (METHOD.md §7 E1, §5 H1): all agents on all built cells, over the frozen contexts, under both conditions and both observation
conditions, at the pre-registered k, producing the paired records from which U, CR and D are computed. This is the experiment the project exists to
run; everything before it is instrument.
Description · Runs in the stage chosen by AWP_STAGE: `pilot` (one agent, one cell, two acts, the pilot context, twenty episodes, written to results/E1/pilot and never mixed with frozen records), `pixels` (the first frozen batch, pixels-only, all built act-cells, both agents, k from configs/prereg.yaml) and `structured`. One episode is a context crossed with a cell, an act, a condition (genuine or replica), an observation condition (pixels, or pixels with
the surface's accessibility tree) and, at the inline browser cell, a sanitiser behaviour. The episode loop is the shared one in
src/awp/harness.py, so E1 and the controls run the same code against the same sinks. The run is resumable: every episode already present in the output
is skipped by its full key, so a run interrupted after hours continues rather than restarting, and the records are written one line at a time. Agents
are served one at a time by the native llama.cpp build at the budget measured for each. Nothing is analysed here: the records are written
and src/awp/analysis.py is the only thing that turns them into rates, after a dated unblinding.
Inputs/Outputs · In: configs/contexts.yaml (the frozen set), configs/cells.yaml, configs/prereg.yaml (k and the floor), the pinned weights. Out:
results/E1/paired/episodes.jsonl, shots/, events-*.jsonl, server logs; progress on stdout.
Depends on · src/awp/harness.py, src/awp/agents.py, src/awp/labapp.py, src/awp/chat.py, src/awp/browser.py, src/awp/mm.py, src/awp/proc.py.
Invariant · The twin pair differs only in the prompt region's principal; the frozen contexts are read and never edited here; no rate is computed in
this file; an episode is written as soon as it ends, so an interruption loses at most one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp import labapp
from awp.agents import LlamaServerAgent
from awp.browser import Browser
from awp.chat import ChatLab
from awp.frontier import AnthropicAgent
from awp.harness import Lab, archive_previous_shots, run_episode, run_episode_chat
from awp.proc import Child

STAGE = os.environ.get("AWP_STAGE", "pixels")  # pilot | pixels | structured
DEFENCE = os.environ.get("AWP_DEFENCE") or None  # E2: the warning defence on the live agents; a defended batch writes its own record under results/E2
OUT = (
    ROOT / "results" / os.environ.get("AWP_RUN_EXP", "E2") / os.environ.get("AWP_RUN_NAME", "warning")
    if DEFENCE
    else ROOT / "results" / "E1" / ("pilot" if STAGE == "pilot" else "paired")
)  # all four batches append to one record; the batch is a factor on each episode  # pilot and frozen records never share a directory (the method);
# a defended batch (E2) is a different treatment and never shares E1's record: its own directory, named by the run
V = ROOT.parent / "alpha-vendor"
BIN = V / "llama.cpp-src" / "build" / "bin" / "llama-server"
M = V / "models"
PORT_A, PORT_B, PORT_LLM = 8441, 8442, 18080
AGENTS = {
    "open_2": (
        "json",
        M / "qwen3-vl-8b-instruct-gguf" / "Qwen3VL-8B-Instruct-Q8_0.gguf",
        M / "qwen3-vl-8b-instruct-gguf" / "mmproj-Qwen3VL-8B-Instruct-F16.gguf",
        ["--image-max-tokens", "512"],
    ),
    "open_1": ("uitars", M / "ui-tars-1.5-7b-gguf" / "UI-TARS-1.5-7B-Q8_0.gguf", M / "ui-tars-1.5-7b-gguf" / "mmproj-UI-TARS-1.5-7B-F16.gguf", []),
}
BROWSER_CELLS = {"browser-l1": ("inline", ("CRED", "PERM", "CONF", "UPDT")), "browser-l2": ("iframe", ("CRED", "PERM", "CONF", "UPDT"))}
CHAT_CELLS = {"chat-l1-web": ("CRED", "PERM", "CONF")}
# the sanitiser contrast changes the tree and never the pixels, so it is crossed with the structured arm only; under pixels-only
# observation the inline cell runs with the stripping sanitiser alone. The structured arm runs where the twins' trees differ.
OBSERVATIONS = {"pilot": ("pixels",), "pixels": ("pixels",), "structured": ("structured",), "provenance": ("provenance",)}[STAGE]  # provenance: E3
SANITISERS = {
    "pixels": {"browser-l1": ("strip",), "browser-l2": ("strip",)},
    "structured": {"browser-l1": ("strip", "pass"), "browser-l2": ("strip",)},
    "provenance": {"browser-l1": ("strip", "pass"), "browser-l2": ("strip",)},
}
PILOT = {"agents": ("open_2",), "cells": {"browser-l2": ("iframe", ("CRED", "PERM"))}, "k": 5}  # stage 1: twenty episodes on the pilot context
# the first frozen batch runs as four short batches by agent and context, each covering only the act-cells that agent cleared at the floor.
BATCHES = {
    "A": ("open_2", "ctx-1"),
    "B": ("open_2", "ctx-2"),
    "C": ("open_1", "ctx-1"),
    "D": ("open_1", "ctx-2"),
    "F": ("anthropic_frontier", "ctx-1"),
    "S1": ("open_2", "ctx-1"),
    "S2": ("open_2", "ctx-2"),
    "S3": ("open_1", "ctx-1"),
    "S4": ("open_1", "ctx-2"),
    "SF": ("anthropic_frontier", "ctx-1"),
    "P1": ("open_2", "ctx-1"),
    "P2": ("open_2", "ctx-2"),
    "P3": ("open_1", "ctx-1"),
    "P4": ("open_1", "ctx-2"),
    "PF": ("anthropic_frontier", "ctx-1"),
}  # F: the frontier arm
BATCH = os.environ.get("AWP_BATCH")  # A | B | C | D for stage pixels; unset runs the whole stage
# 's stopping rule: the act-cells it extends are named here as cell:act pairs and run at the raised k; the resumable key keeps the
# repetitions already recorded and adds the new ones, so an extension never repeats an episode
ONLY_ACTCELLS = {tuple(x.split(":")) for x in os.environ.get("AWP_ACTCELLS", "").split(",") if x}
K_OVERRIDE = int(os.environ["AWP_K"]) if os.environ.get("AWP_K") else None
FLOOR_RUNS = sorted((ROOT / "results" / "E0").glob("utility-floor-*/episodes.jsonl"))  # every floor run, open and frontier, completions included
FRONTIER = "anthropic_frontier"


def cleared_at_floor(u0):
    """Per agent, the (cell, act) pairs whose utility at the floor runs reached u0; a pair below it carries no confusion rate and is not run
   . Every floor run is read, so an agent's completion runs count with its main one."""
    if not FLOOR_RUNS:
        return None
    tally = {}
    for path in FLOOR_RUNS:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                k = (r["agent"], r["cell"], r["act"])
                n, y = tally.get(k, (0, 0))
                tally[k] = (n + 1, y + int(r["y"]))
    return {k for k, (n, y) in tally.items() if n >= 3 and y / n >= u0}


CONDITIONS = ("genuine", "replica")
KEY = ("cell", "act", "agent", "observation", "sanitiser", "context", "condition", "rep")


def pinned_frontier():
    import re

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


def cfg(name):
    return yaml.safe_load((ROOT / "configs" / f"{name}.yaml").read_text(encoding="utf-8"))


def done_keys():
    p = OUT / "episodes.jsonl"
    if not p.exists():
        return set()
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("observation") in ("structured", "provenance") and not r.get("structure_units"):
                continue  # : a tree-carrying episode that never recorded its coordinate frame measured the instrument; it is redone, never resumed past
            steps = r.get("steps") or []
            if steps and all(str((s.get("action") or {}).get("why", "")).startswith("request failed") for s in steps):
                continue  # measured (batch SF): a frontier episode whose every step failed before a request (the SDK missing from the
                # interpreter) measured nothing and spent nothing; it is redone, never resumed past, and the analysis already counts it as no_data
            out.add(tuple(str(r.get(k)) for k in KEY))
    return out


def start_server(model, mmproj, extra, log_path):
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    child = Child(
        [
            str(BIN),
            "-m",
            str(model),
            "--mmproj",
            str(mmproj),
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT_LLM),
            "-t",
            "10",
            "-tb",
            "10",
            "-c",
            "4096",
            "-np",
            "1",
            "-ngl",
            "0",
            *extra,
        ],
        864000,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    t0 = time.time()
    while time.time() - t0 < 900:
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{PORT_LLM}/health", timeout=3).status == 200:
                return child, log, round(time.time() - t0, 1)
        except OSError:
            time.sleep(1.0)
        if child.proc.poll() is not None:
            break
    raise RuntimeError("llama-server did not come up")


def scrub(path):
    if path.exists():
        t = path.read_text(encoding="utf-8", errors="replace")
        path.write_text(t.replace(str(ROOT.parent), "..").replace(str(Path.home()), "~"), encoding="utf-8")


def plan(contexts, k, cleared=None):
    """Every episode this run would do, in a fixed order, so a resumed run continues where it stopped."""
    items = []
    agents = PILOT["agents"] if STAGE == "pilot" else tuple(AGENTS)
    if STAGE in ("pixels", "structured", "provenance") and BATCH:  # S1 to SF are the structured arm
        agent_only, ctx_only = BATCHES[BATCH]
        agents = (agent_only,)
        wanted = os.environ.get("AWP_CONTEXTS", ctx_only).split(",")  # an extension spans both contexts of the agent
        contexts = [c for c in contexts if c["id"] in wanted]
    browser_cells = PILOT["cells"] if STAGE == "pilot" else BROWSER_CELLS
    chat_cells = (
        {} if STAGE in ("pilot", "structured", "provenance") or DEFENCE else CHAT_CELLS
    )  # the chat twins are unmatched and their tree adds nothing; a defence cannot be measured on an unmatched twin either
    sanitisers = SANITISERS["pixels" if STAGE == "pilot" else STAGE]
    for agent in agents:
        for observation in OBSERVATIONS:
            for cell, (level, acts) in browser_cells.items():
                for sanitiser in sanitisers[cell]:
                    for act in acts:
                        if cleared is not None and (agent, cell, act) not in cleared:
                            continue
                        if ONLY_ACTCELLS and (cell, act) not in ONLY_ACTCELLS:
                            continue
                        for ctx in contexts:
                            for condition in CONDITIONS:
                                for rep in range(1, k + 1):
                                    items.append(
                                        {
                                            "kind": "browser",
                                            "agent": agent,
                                            "observation": observation,
                                            "cell": cell,
                                            "level": level,
                                            "sanitiser": sanitiser,
                                            "act": act,
                                            "context": ctx,
                                            "condition": condition,
                                            "rep": rep,
                                        }
                                    )
            for cell, acts in chat_cells.items():
                for act in acts:
                    if cleared is not None and (agent, cell, act) not in cleared:
                        continue
                    if ONLY_ACTCELLS and (cell, act) not in ONLY_ACTCELLS:
                        continue
                    for ctx in contexts:
                        for condition in CONDITIONS:
                            for rep in range(1, k + 1):
                                items.append(
                                    {
                                        "kind": "chat",
                                        "agent": agent,
                                        "observation": observation,
                                        "cell": cell,
                                        "level": "L1",
                                        "sanitiser": None,
                                        "act": act,
                                        "context": ctx,
                                        "condition": condition,
                                        "rep": rep,
                                    }
                                )
    return items


def main():
    contexts = cfg("contexts")["pilot" if STAGE == "pilot" else "frozen"]
    pre = cfg("prereg")
    k = PILOT["k"] if STAGE == "pilot" else (K_OVERRIDE or int(pre["k_runs_open"]))
    print(f"stage {STAGE}: contexts {[c['id'] for c in contexts]}, k {k}, observation {OBSERVATIONS}", flush=True)
    limit = int(os.environ.get("AWP_LIMIT", "0")) or None
    OUT.mkdir(parents=True, exist_ok=True)
    shots = OUT / "shots"
    shots.mkdir(exist_ok=True)
    if not (OUT / "episodes.jsonl").exists():
        archive_previous_shots(shots)
    web_events, chat_events = OUT / "events-labapp.jsonl", OUT / "events-chat.jsonl"
    for p in (web_events, chat_events):
        if not p.exists():
            p.write_text("", encoding="utf-8")
    cleared = cleared_at_floor(float(pre["utility_floor"])) if STAGE != "pilot" else None
    if STAGE != "pilot" and cleared is None:
        print("SUMMARY " + json.dumps({"status": "floor_missing", "note": "the utility floor run must exist before a frozen batch"}))
        return 1
    items = plan(contexts, k, cleared)
    print(f"batch {BATCH or 'all'}: act-cells cleared at the floor: {sorted(c for c in (cleared or []))}", flush=True)
    already = done_keys()
    todo = [
        it
        for it in items
        if tuple(str(v) for v in (it["cell"], it["act"], it["agent"], it["observation"], it["sanitiser"], it["context"]["id"], it["condition"], it["rep"]))
        not in already
    ]
    print(f"plan {len(items)} episodes; {len(already)} already recorded; {len(todo)} to run", flush=True)
    if limit:
        todo = todo[:limit]
        print(f"limited to {len(todo)} this invocation (AWP_LIMIT)", flush=True)
    if not todo:
        print("SUMMARY " + json.dumps({"status": "complete", "episodes": len(already)}))
        return 0
    servers, _ = labapp.serve(PORT_A, PORT_B, str(web_events))
    lab = Lab(PORT_A, PORT_B)
    chat = ChatLab(str(chat_events), server_deadline_s=864000) if any(it["kind"] == "chat" for it in todo) else None
    browser = Browser(deadline_s=864000)
    n = 0
    try:
        for agent_name in sorted({it["agent"] for it in todo}, key=lambda n: (list(AGENTS) + [FRONTIER]).index(n)):
            mine = [it for it in todo if it["agent"] == agent_name]
            if not mine:
                continue
            if agent_name == FRONTIER:
                srv, log, load_s = None, None, 0.0
                model_id, price = pinned_frontier()
                agent = AnthropicAgent(agent_name, model_id, browser.width, browser.height)
                print(f"{agent_name}: {model_id} through the vendor path, {len(mine)} episodes", flush=True)
            else:
                style, model, mmproj, extra = AGENTS[agent_name]
                srv, log, load_s = start_server(model, mmproj, extra, OUT / f"{agent_name}.server.log")
                agent = LlamaServerAgent(agent_name, f"http://127.0.0.1:{PORT_LLM}", style, browser.width, browser.height, defence=DEFENCE)
                print(f"{agent_name}: server up in {load_s} s, {len(mine)} episodes", flush=True)
            try:
                with open(OUT / "episodes.jsonl", "a", encoding="utf-8") as fh:
                    for it in mine:
                        t0 = time.time()
                        if agent_name == FRONTIER:
                            cap = float(os.environ.get("AWP_MAX_USD", "0") or 0) or None
                            if cap and agent.spend_usd(price) >= cap:  # the declared cap is a stop inside the run, not only an admission check
                                print(f"stopped at the declared cap: {agent.spend_usd(price):.3f} USD of {cap:.2f}", flush=True)
                                break
                        if it["kind"] == "browser":
                            row = run_episode(
                                browser,
                                lab,
                                agent,
                                it["cell"],
                                it["level"],
                                it["act"],
                                it["condition"],
                                it["rep"],
                                shots,
                                tag="e1-",
                                context=it["context"],
                                observation=it["observation"],
                                sanitiser=it["sanitiser"],
                            )
                        else:
                            row = run_episode_chat(
                                browser,
                                chat,
                                lab.control,
                                lab.b,
                                agent,
                                it["act"],
                                it["condition"],
                                it["rep"],
                                shots,
                                tag="e1-",
                                context=it["context"],
                                observation=it["observation"],
                            )
                            row["sanitiser"] = None
                        row["load_s"] = load_s
                        row["batch"] = BATCH
                        row["defence"] = DEFENCE
                        fh.write(json.dumps(row, sort_keys=True) + "\n")
                        fh.flush()
                        n += 1
                        print(
                            f"[{n}/{len(todo)}] {agent_name} {it['observation']} {it['cell']} {it['sanitiser'] or '-'} {it['act']} {it['context']['id']} {it['condition']} rep{it['rep']}: y={row['y']} {row['stop']} {row['n_steps']} steps {round(time.time() - t0)}s",
                            flush=True,
                        )
            finally:
                if srv is not None:
                    srv.stop()
                    log.close()
                    scrub(OUT / f"{agent_name}.server.log")
                if agent_name == FRONTIER:
                    usd = agent.spend_usd(price)
                    (
                        ROOT / "results" / os.environ.get("AWP_RUN_EXP", "E1") / f"{os.environ.get('AWP_RUN_NAME', 'paired')}.usage.json"
                    ).write_text(  # beside the run's provenance (E3's PF runs under E3)
                        json.dumps({"usd_spent": usd, **agent.usage, "price_usd_per_mtok": price}, indent=1, sort_keys=True), encoding="utf-8"
                    )
    finally:
        browser.close()
        if chat:
            chat.stop()
        for s in servers:
            s.shutdown()
    print(
        "SUMMARY " + json.dumps({"stage": STAGE, "status": "partial" if limit else "done", "ran": n, "recorded_total": len(done_keys()), "planned": len(items)})
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
