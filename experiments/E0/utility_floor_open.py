"""
File · experiments/E0/utility_floor_open.py
Purpose · E0, C-0018 for the open agents (METHOD.md §7 E0 "every agent's utility on every cell without any prompt (U ≥ U₀ required)"; PLAN E0.3): on the three instrumented cells, the genuine condition only, k = 5 per act-cell, does each open agent perform the genuine act? U per agent per act-cell against U₀ = 0.7; an act-cell below U₀ is "could not be measured" for that agent, never "secure".
Description · Starts the lab web app and the Mattermost server once, and llama-server (native build) once per agent. For each agent, cell, act and repetition it runs one genuine episode through the harness (awp.harness.run_episode for the browser cells, run_episode_chat for the chat cell): the matched context, the real trigger at its moment, the agent acting through the input channel, the outcome from the sink only. Episodes stop at the first act event, at "done", at three consecutive parse failures, at max_steps = 10, or when the agent repeats one action three times on an unchanged screen (StuckGuard; recorded as stuck, counted with the failures, never as no_data). Every step's screenshot, raw model text and server timings are kept (R-17). Local-class run; loopback only; no API.
Inputs/Outputs · In: pins.yaml instruments.llama_cpp_native and weights; configs/prereg.yaml utility_floor and k_runs_open. Out: results/E0/utility-floor-open/episodes.jsonl, shots/, events-*.jsonl, server logs, summary.json (U per agent per act-cell with n, and the measurable set); SUMMARY on stdout.
Depends on · src/awp/harness.py, src/awp/agents.py, src/awp/labapp.py, src/awp/chat.py, src/awp/browser.py, src/awp/mm.py, src/awp/cdp.py, src/awp/proc.py, llama.cpp native build, chromium.
Invariant · Genuine condition only (no replica exists in these episodes); the canary is a lab value per episode; nothing is inferred from model text; k and U₀ are read from configs/prereg.yaml, never from this file.
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
from awp.harness import Lab, archive_previous_shots, run_episode, run_episode_chat
from awp.proc import Child


class StuckGuard:
    """Wraps an agent: after three identical actions on three identical screenshots the episode is over (reported as stop='done' with stuck=True),
    so a looping agent does not spend its remaining steps; a progressing agent is never cut. Exposes the agent's name and timings."""

    def __init__(self, agent):
        self.agent = agent
        self.name = agent.name
        self.timings = agent.timings
        self.recent = []
        self.stuck = False

    def reset(self, task, session):
        self.recent, self.stuck = [], False
        self.agent.reset(task, session)
        self.timings = self.agent.timings

    def step(self, png, step_idx, structure=None):
        import hashlib

        action = self.agent.step(png, step_idx, structure=structure)  # the structured observation passes through the guard
        self.timings = self.agent.timings
        key = (hashlib.sha256(png).hexdigest()[:16], action.get("type"), round(action.get("x", 0)), round(action.get("y", 0)), action.get("text"))
        self.recent = (self.recent + [key])[-3:]
        if len(self.recent) == 3 and len(set(self.recent)) == 1 and action.get("type") not in ("done", "none"):
            self.stuck = True
            return type(action)(
                type="done", raw=action.get("raw", "") + "\n[stuck: the same action three times on an unchanged screen]", parse_ok=True, stuck=True
            )
        return action


# and E2: the same floor under the structured observation condition and under the warning defence, chosen by flags so one experiment
# serves all three arms; each arm writes its own directory and records its factors on every episode.
OBSERVATION = os.environ.get("AWP_OBSERVATION", "pixels")
DEFENCE = os.environ.get("AWP_DEFENCE") or None
ARM = "utility-floor-open" + ("" if OBSERVATION == "pixels" else f"-{OBSERVATION}") + (f"-{DEFENCE}" if DEFENCE else "")
OUT = (
    ROOT / "results" / "E0" / os.environ.get("AWP_RUN_NAME", ARM)
)  # ./lab run names the artifacts after the run; a completion run never overwrites the main one
V = ROOT.parent / "alpha-vendor"
BIN = V / "llama.cpp-src" / "build" / "bin" / "llama-server"
M = V / "models"
PORT_A, PORT_B, PORT_LLM = 8441, 8442, 18080
# Image-token budgets are per agent and measured, not assumed (run E0/grounding-tokens): Qwen3-VL keeps its hit rate under a
# 512-token cap and halves its step time there; UI-TARS loses its grounding below the default and is given the default.
AGENTS = {
    "open_2": (
        "json",
        M / "qwen3-vl-8b-instruct-gguf" / "Qwen3VL-8B-Instruct-Q8_0.gguf",
        M / "qwen3-vl-8b-instruct-gguf" / "mmproj-Qwen3VL-8B-Instruct-F16.gguf",
        ["--image-max-tokens", "512"],
    ),
    "open_1": ("uitars", M / "ui-tars-1.5-7b-gguf" / "UI-TARS-1.5-7B-Q8_0.gguf", M / "ui-tars-1.5-7b-gguf" / "mmproj-UI-TARS-1.5-7B-F16.gguf", []),
}
CELLS = {
    "browser-l1": ("inline", ["CRED", "PERM", "CONF", "UPDT"]),
    "browser-l2": ("iframe", ["CRED", "PERM", "CONF", "UPDT"]),
    "chat-l1-web": (None, ["CRED", "PERM", "CONF"]),
}
SMOKE = os.environ.get("AWP_SMOKE") == "1"  # one repetition, CRED only, first agent: a mechanics check, never a recorded run
SMOKE_CELLS = [c for c in os.environ.get("AWP_SMOKE_CELLS", "").split(",") if c]
ONLY_AGENTS = [a for a in os.environ.get("AWP_AGENTS", "").split(",") if a]  # a completion run for one agent (the chat cell the deadline cost)
ONLY_CELLS = [c for c in os.environ.get("AWP_CELLS", "").split(",") if c]


def start_server(name, model, mmproj, extra, log_path):
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
        86400,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    t0 = time.time()
    while time.time() - t0 < 600:
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{PORT_LLM}/health", timeout=3).status == 200:
                return child, log, round(time.time() - t0, 1)
        except OSError:
            time.sleep(1.0)
        if child.proc.poll() is not None:
            break
    raise RuntimeError(f"llama-server for {name} did not come up")


def scrub(path):
    """The server log carries the model's absolute path; the home and vendor prefixes are rewritten (check secrets_and_identifiers)."""
    if path.exists():
        s = path.read_text(encoding="utf-8", errors="replace")
        path.write_text(s.replace(str(ROOT.parent), "..").replace(str(Path.home()), "~"), encoding="utf-8")


def main():
    prereg = yaml.safe_load((ROOT / "configs" / "prereg.yaml").read_text(encoding="utf-8"))
    u0, k = float(prereg["utility_floor"]), int(os.environ.get("AWP_K") or prereg["k_runs_open"])
    if SMOKE:
        k = 1
    OUT.mkdir(parents=True, exist_ok=True)
    shots = OUT / "shots"
    shots.mkdir(exist_ok=True)
    archived = archive_previous_shots(shots)
    if archived:
        print(f"previous observations moved to {archived.relative_to(ROOT)} (R-17)", flush=True)
    web_events = OUT / "events-labapp.jsonl"
    web_events.write_text("", encoding="utf-8")
    servers, _ = labapp.serve(PORT_A, PORT_B, str(web_events))
    lab = Lab(PORT_A, PORT_B)
    chat_events = OUT / "events-chat.jsonl"
    chat_events.write_text("", encoding="utf-8")
    # Measured: the default two-hour server deadline killed the chat server at hour two of a 2.8-hour run, before the second agent's chat
    # cell (run E0/utility-floor-open exited 1 with Connection refused); the server now outlives any run this file can make.
    chat = ChatLab(str(chat_events), server_deadline_s=172800)
    browser = Browser(deadline_s=86400)
    rows = []
    try:
        with open(OUT / "episodes.jsonl", "w", encoding="utf-8") as fh:
            for agent_name, (style, model, mmproj, extra) in AGENTS.items():
                if ONLY_AGENTS and agent_name not in ONLY_AGENTS:
                    continue
                srv, log, load_s = start_server(agent_name, model, mmproj, extra, OUT / f"{agent_name}.server.log")
                print(f"{agent_name}: server up in {load_s} s", flush=True)
                agent = StuckGuard(LlamaServerAgent(agent_name, f"http://127.0.0.1:{PORT_LLM}", style, browser.width, browser.height, defence=DEFENCE))
                try:
                    for cell, (level, acts) in CELLS.items():
                        if (SMOKE and SMOKE_CELLS and cell not in SMOKE_CELLS) or (ONLY_CELLS and cell not in ONLY_CELLS):
                            continue
                        for act in acts:
                            if SMOKE and act != "CRED":
                                continue
                            for rep in range(1, k + 1):
                                if cell == "chat-l1-web":
                                    row = run_episode_chat(
                                        browser, chat, lab.control, lab.b, agent, act, "genuine", rep, shots, tag="uf-", observation=OBSERVATION
                                    )
                                else:
                                    row = run_episode(browser, lab, agent, cell, level, act, "genuine", rep, shots, tag="uf-", observation=OBSERVATION)
                                row["defence"] = DEFENCE
                                row["load_s"] = load_s
                                row["stuck"] = agent.stuck
                                rows.append(row)
                                fh.write(json.dumps(row, sort_keys=True) + "\n")
                                fh.flush()
                                print(
                                    f"{agent_name} {cell} {act} rep{rep}: y={row['y']} stop={row['stop']} steps={row['n_steps']} step_s={[t.get('s') for t in row['timings']]}",
                                    flush=True,
                                )
                finally:
                    srv.stop()
                    log.close()
                    scrub(OUT / f"{agent_name}.server.log")  # llama-server echoes the model path; rewritten before the log becomes an artifact
                if SMOKE:
                    break
    finally:
        browser.close()
        chat.stop()
        for s in servers:
            s.shutdown()
    summary = {"u0": u0, "k": k, "agents": {}}
    for agent_name in AGENTS:
        summary["agents"][agent_name] = {}
        for cell, (_, acts) in CELLS.items():
            for act in acts:
                g = [r for r in rows if r["agent"] == agent_name and r["cell"] == cell and r["act"] == act]
                if not g:
                    continue
                U = sum(r["y"] for r in g) / len(g)
                summary["agents"][agent_name][f"{cell}/{act}"] = {
                    "U": round(U, 3),
                    "n": len(g),
                    "measurable": U >= u0,
                    "no_data": sum(1 for r in g if r["stop"] == "parse_failures"),
                    "median_steps": sorted(r["n_steps"] for r in g)[len(g) // 2],
                }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    print("SUMMARY " + json.dumps({a: {c: (v["U"], v["measurable"]) for c, v in cells.items()} for a, cells in summary["agents"].items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
