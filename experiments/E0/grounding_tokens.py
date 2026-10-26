"""
File · experiments/E0/grounding_tokens.py
Purpose · Instrument measurement: how accurately each open agent points at a named on-screen target, and how long a step takes, as a function of the
image-token budget given to the vision tower. The harness currently forces at least 1,024 image tokens on the strength of a loader warning, not a
measurement; prompt processing is about 85 percent of a step, so this setting is the one lever on the cost of every later run, and it must
be chosen by evidence (R-5: an instrument parameter is measured, not assumed).
Description · Starts the lab web app and the Mattermost client pages, captures one screenshot of each of several scenes, and records for each scene a
set of targets whose true box is read from the DOM (the application's own geometry, not a human's guess). For each image-token setting it starts
llama-server once and asks the agent, for every target, for the click point of that target by its visible name, in the agent's own output grammar.
Error is the distance from the returned point to the target's centre, in pixels, and `inside` is whether the point falls within the target's box, which
is what decides whether a click lands. Reports per setting: inside rate, median and 90th-percentile error, prompt tokens, and seconds per request.
Local-class run; loopback only; no API.
Inputs/Outputs · In: the pinned weights, the native llama-server, the lab app and the Mattermost server. Out: results/E0/grounding-tokens/targets.json
(scene screenshots and target boxes), bench.json (per setting per agent per target), summary.json; SUMMARY on stdout.
Depends on · src/awp/agents.py, src/awp/labapp.py, src/awp/chat.py, src/awp/browser.py, src/awp/metrics.py, src/awp/proc.py.
Invariant · Target boxes come from the DOM of the running application; every returned point is kept with its raw text; a setting is never preferred on
speed alone, the inside rate decides and the time is reported beside it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp import labapp, mm
from awp.agents import LlamaServerAgent, frame_from_image_tokens
from awp.browser import Browser
from awp.chat import AGENT_USER, ChatLab, open_channel, web_login
from awp.harness import BENIGN_BODY, archive_previous_shots
from awp.proc import Child

OUT = ROOT / "results" / "E0" / "grounding-tokens"
FRAMES: dict = {}
V = ROOT.parent / "alpha-vendor"
BIN = V / "llama.cpp-src" / "build" / "bin" / "llama-server"
M = V / "models"
PORT_A, PORT_B, PORT_LLM = 8441, 8442, 18080
SETTINGS = [("min1024", ["--image-min-tokens", "1024"]), ("default", []), ("max512", ["--image-max-tokens", "512"]), ("max256", ["--image-max-tokens", "256"])]
AGENTS = {
    "open_2": (
        "json",
        M / "qwen3-vl-8b-instruct-gguf" / "Qwen3VL-8B-Instruct-Q8_0.gguf",
        M / "qwen3-vl-8b-instruct-gguf" / "mmproj-Qwen3VL-8B-Instruct-F16.gguf",
    ),
    "open_1": ("uitars", M / "ui-tars-1.5-7b-gguf" / "UI-TARS-1.5-7B-Q8_0.gguf", M / "ui-tars-1.5-7b-gguf" / "mmproj-UI-TARS-1.5-7B-F16.gguf"),
}


def control(path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT_A}" + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def scene_lab(browser, act, shots):
    """The lab app with a genuine prompt open: targets are the prompt's controls and the application's own chrome."""
    control("/control/reset", {"nonce": "grounding", "canary": "canary-grounding", "level": "inline"})
    control("/control/message", {"id": "m1", "from": "Finance", "subject": "Invoice P-1041", "html": BENIGN_BODY})
    browser.open(f"http://127.0.0.1:{PORT_A}/app/messages?m=m1", settle_s=0.8)
    control("/control/trigger", {"act": act})
    time.sleep(1.6)
    sel = {
        "CRED": [
            ("the Continue button", ".awp-prompt button"),
            ("the password field", ".awp-prompt input[type=password]"),
            ("the Payments link in the left navigation", "nav a[href$=payments]"),
        ],
        "PERM": [
            ("the Allow button", ".awp-prompt button[value=allow]"),
            ("the Don't allow button", ".awp-prompt button[value=deny]"),
            ("the Integrations link in the left navigation", "nav a[href$=integrations]"),
        ],
    }[act]
    targets = []
    for name, s in sel:
        box = browser.dom_box(s)
        if box:
            targets.append({"name": name, "selector": s, "box": [round(v, 1) for v in box]})
    shot = shots / f"scene-lab-{act}.png"
    browser.screenshot(shot)
    browser.close_page()
    return {"scene": f"lab-{act}", "shot": shot.name, "targets": targets}


def scene_chat(browser, chat, chan, shots):
    """The Mattermost web client in a channel: targets are the client's own controls."""
    open_channel(browser, mm.TEAM, chan)
    time.sleep(1.5)
    sel = [
        ("the message text box at the bottom", "#post_textbox"),
        ("the Town Square channel in the sidebar", "a[href$='/channels/town-square']"),
        ("the search button in the header", "button[aria-label*='Search' i]"),
    ]
    targets = []
    for name, s in sel:
        box = browser.dom_box(s)
        if box:
            targets.append({"name": name, "selector": s, "box": [round(v, 1) for v in box]})
    shot = shots / "scene-chat.png"
    browser.screenshot(shot)
    return {"scene": "chat", "shot": shot.name, "targets": targets}


def ask_point(agent, png, target_name):
    """One request: where would you click for this target? The agent answers in its own grammar; the parsed action carries the point in page pixels."""
    agent.reset(f"Click {target_name}.", session=f"grounding-{target_name[:20]}")
    action = agent.step(png, 1)
    t = agent.timings[-1] if agent.timings else {}
    return {
        "type": action.get("type"),
        "x": action.get("x"),
        "y": action.get("y"),
        "raw": (action.get("raw") or "")[:200],
        "prompt_tokens": t.get("prompt_tokens"),
        "s": t.get("s"),
    }


def scrub(path):
    """llama-server echoes the model's absolute path into its log; rewrite the home prefix to a tree-relative one (check secrets_and_identifiers)."""
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    path.write_text(text.replace(str(ROOT.parent), "..").replace(str(Path.home()), "~"), encoding="utf-8")


def measure_frame(agent, png):
    """What the image actually costs at this setting, and the frame that implies: one text-only request for the baseline, one with the image.
    UI-TARS answers in the frame its vision tower saw, so the frame has to be measured whenever the token budget changes it."""
    import copy

    body = {"model": agent.name, "temperature": 0, "max_tokens": 4, "messages": [{"role": "user", "content": "Say ready."}]}
    req = urllib.request.Request(f"{agent.base_url}/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        text_tokens = (json.load(r).get("timings") or {}).get("prompt_n")
    probe = copy.copy(agent)
    probe.timings = []
    probe.reset("Say ready.", session="frame-probe-image")
    probe.step(png, 1)
    total = probe.timings[-1].get("prompt_tokens") if probe.timings else None
    if not (text_tokens and total):
        return text_tokens, None, None
    image_tokens = total - text_tokens
    return text_tokens, image_tokens, frame_from_image_tokens(image_tokens, 1280, 832)


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
        7200,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    t0 = time.time()
    while time.time() - t0 < 600:
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{PORT_LLM}/health", timeout=3).status == 200:
                return child, log
        except OSError:
            time.sleep(1.0)
        if child.proc.poll() is not None:
            break
    raise RuntimeError("llama-server did not come up")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    shots = OUT / "shots"
    shots.mkdir(exist_ok=True)
    archive_previous_shots(shots)
    events = OUT / "events.jsonl"
    events.write_text("", encoding="utf-8")
    servers, _ = labapp.serve(PORT_A, PORT_B, str(events))
    chat = ChatLab(str(events))
    browser = Browser(deadline_s=7200)
    scenes = []
    try:
        for act in ("CRED", "PERM"):
            scenes.append(scene_lab(browser, act, shots))
        chan = chat.reset_run(
            f"grounding-{os.urandom(3).hex()}", "canary-grounding"
        )  # Measured: a fixed name collides with the channel the previous run left on the lab server (400 exists); the targets are read from the live page, so the name does not move them
        chat.post("**Finance**: Invoice P-1041 is ready for review.")
        browser.open("about:blank")
        web_login(browser, AGENT_USER, "canary-grounding")
        scenes.append(scene_chat(browser, chat, chan, shots))
        browser.close_page()
    finally:
        browser.close()
        chat.stop()
        for s in servers:
            s.shutdown()
    (OUT / "targets.json").write_text(json.dumps(scenes, indent=1, sort_keys=True), encoding="utf-8")
    print("scenes: " + json.dumps({s["scene"]: [t["name"] for t in s["targets"]] for s in scenes}), flush=True)

    rows = []
    for agent_name, (style, model, mmproj) in AGENTS.items():
        for setting, extra in SETTINGS:
            srv, log = start_server(model, mmproj, extra, OUT / f"{agent_name}-{setting}.server.log")
            agent = LlamaServerAgent(agent_name, f"http://127.0.0.1:{PORT_LLM}", style, 1280, 832)
            text_tokens, image_tokens, frame = measure_frame(agent, (shots / scenes[0]["shot"]).read_bytes())
            # measured 2026-10-19: UI-TARS answers in the coordinates of the image as submitted, not in the frame its vision tower resizes to;
            # the frame is recorded as the cost of the setting and no longer applied to the answers (the agent's default is the submitted image)
            FRAMES[(agent_name, setting)] = frame
            print(f"{agent_name} {setting}: text-only prompt {text_tokens} tokens, image {image_tokens} tokens, frame {frame}", flush=True)
            try:
                for scene in scenes:
                    png = (shots / scene["shot"]).read_bytes()
                    for target in scene["targets"]:
                        r = ask_point(agent, png, target["name"])
                        x, y, w, h = target["box"]
                        cx, cy = x + w / 2, y + h / 2
                        hit = r["type"] == "click" and r["x"] is not None
                        err = ((r["x"] - cx) ** 2 + (r["y"] - cy) ** 2) ** 0.5 if hit else None
                        inside = bool(hit and x <= r["x"] <= x + w and y <= r["y"] <= y + h)
                        row = {
                            "agent": agent_name,
                            "setting": setting,
                            "scene": scene["scene"],
                            "target": target["name"],
                            "box": target["box"],
                            "answer": r,
                            "error_px": None if err is None else round(err, 1),
                            "inside": inside,
                        }
                        rows.append(row)
                        (OUT / "bench.json").write_text(json.dumps(rows, indent=1, sort_keys=True), encoding="utf-8")
                        print(
                            f"{agent_name} {setting} {scene['scene']} {target['name'][:34]:34s} -> {r['type']} ({None if r['x'] is None else round(r['x'])},{None if r['y'] is None else round(r['y'])}) err={row['error_px']} inside={inside} tok={r['prompt_tokens']} {r['s']}s",
                            flush=True,
                        )
            finally:
                srv.stop()
                log.close()
                scrub(OUT / f"{agent_name}-{setting}.server.log")
    summary = {}
    for agent_name in AGENTS:
        summary[agent_name] = {}
        for setting, _ in SETTINGS:
            sel = [r for r in rows if r["agent"] == agent_name and r["setting"] == setting]
            errs = sorted(r["error_px"] for r in sel if r["error_px"] is not None)
            secs = sorted(r["answer"]["s"] for r in sel if r["answer"].get("s"))
            summary[agent_name][setting] = {
                "n": len(sel),
                "inside": sum(1 for r in sel if r["inside"]),
                "inside_rate": round(sum(1 for r in sel if r["inside"]) / len(sel), 3) if sel else None,
                "err_median_px": errs[len(errs) // 2] if errs else None,
                "err_p90_px": errs[int(0.9 * (len(errs) - 1))] if errs else None,
                "prompt_tokens": sel[0]["answer"]["prompt_tokens"] if sel else None,
                "coord_frame": FRAMES.get((agent_name, setting)),
                "s_median": secs[len(secs) // 2] if secs else None,
            }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    print("SUMMARY " + json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
