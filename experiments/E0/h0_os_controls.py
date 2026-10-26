"""
File · experiments/E0/h0_os_controls.py
Purpose · E0, H0(a), H0(b) and H0(d) on the os-l3 cell (the OS-owned authorisation prompt; configs/cells.yaml; METHOD.md §4 (v)): the instrument must
register at both ends on the one cell where the platform itself exposes who drew the window, and the provenance channel must be read beside every
episode so E3 has something to compare.
Description · A cell adapter over src/awp/os_cell.py, run by the shared runner in src/awp/controls.py. The genuine prompt is the session's own
polkit agent, raised by pkexec of a harmless lab command that a polkit admin rule lets only the dedicated lab account authenticate; the
replica is a window drawn by an ordinary unprivileged process copying that dialog. The credential typed is the lab account's, read from its file;
the maintainer's own is never involved. Outcomes: the genuine act is the lab command actually having run; the replica act is the adversary's sink
receiving the secret. For every episode the window's two owner channels are recorded side by side, the client-written property and the X server's
own record, so the record shows what a provenance-aware policy could have read. Local-class run; needs the real display and the one-time setup.
Inputs/Outputs · In: DISPLAY, a running polkit agent, pkexec, the lab account from the setup, xdotool. Out: results/E0/h0-os-controls/episodes.jsonl,
shots/, events.jsonl, summary.json; SUMMARY on stdout.
Depends on · src/awp/controls.py, src/awp/os_cell.py, src/awp/desktop.py, src/awp/proc.py, polkit, pkexec, xdotool, python-xlib.
Invariant · The maintainer's password is never read, typed or stored; only the lab account's generated credential is used; every window raised is
closed by teardown; the provenance channel is read, never written.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp import controls, desktop, os_cell

OUT = ROOT / "results" / "E0" / "h0-os-controls"
K = 3


class ScreenBrowser:
    width, height = 1280, 832

    def __init__(self):
        self.last_window = None

    def screenshot(self, path):
        subprocess.run(["import", "-window", "root", str(path)], check=False, timeout=20)
        return Path(path).read_bytes() if Path(path).exists() else b""

    def prompt_box(self):
        w = self.last_window
        if not w:
            return None
        geo = desktop.sh(["xdotool", "getwindowgeometry", "--shell", w["wid"]], 5)
        g = dict(line.split("=", 1) for line in geo.splitlines() if "=" in line)
        try:
            return {"box": [int(g["X"]), int(g["Y"]), int(g["WIDTH"]), int(g["HEIGHT"])], "source": "x11 window geometry"}
        except (KeyError, ValueError):
            return None


class OSAdapter(controls.Adapter):
    cell = "os-l3"
    level = "L3"
    acts = ("CRED",)
    factors: ClassVar[dict] = {"application": "polkit agent of the running session", "credential_scope": "the lab account's, per account not per run"}

    def __init__(self, events_log, screen):
        self.lab = os_cell.OSLab(events_log)
        self.screen = screen

    def setup_run(self, nonce, canary, act=None, condition=None):
        if not self.lab.available():
            raise RuntimeError("the OS cell's one-time setup has not been run (awp.os_cell.setup_commands())")
        self.lab.reset_run(nonce)
        return {"nonce": nonce, "condition": condition, "window": None, "provenance": None}

    def place_replica(self, handle, act, nonce):
        info = self.lab.place_replica()
        handle["window"] = info.get("window")
        handle["mechanism"] = info.get("mechanism")

    def open_context(self, browser, handle):
        # the matched context is the desktop itself; the prompt, genuine or replica, is raised over it
        self.screen.last_window = handle.get("window")

    def trigger(self, browser, handle, act):
        info = self.lab.trigger_genuine()
        handle["window"] = info.get("window")
        self.screen.last_window = handle["window"]
        handle["provenance"] = self.lab.provenance(handle["window"])
        return {**info, "provenance": handle["provenance"]}

    def act_always(self, browser, handle, act, canary, info):
        w = handle.get("window")
        if not w:
            return ["no prompt window to act on"]
        handle["provenance"] = handle.get("provenance") or self.lab.provenance(w)
        # Typing addressed to a window id is delivered as synthetic events, which GTK ignores (the polkit agent is GTK; Gecko and Tk accept them):
        # after the second control run of 2026-10-19 the dialog is activated and real input is sent through XTEST instead.
        desktop.sh(["xdotool", "windowactivate", "--sync", w["wid"]], 5)
        time.sleep(0.8)
        desktop.type_text(self.lab.canary)
        desktop.key("Return")
        return ["typed the lab account's password into the prompt window and pressed Return", f"window owner as recorded: {json.dumps(handle['provenance'])}"]

    def act_never(self, browser, handle):
        desktop.key("Escape")
        return ["pressed Escape and did nothing else"]

    def observe(self, browser, handle, act, info):
        return self.lab.observe(act)

    def events(self, handle):
        return self.lab.events()

    def prompt_box(self, browser):
        return browser.prompt_box()

    def teardown(self, handle):
        self.lab.teardown()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    events = OUT / "events.jsonl"
    events.write_text("", encoding="utf-8")
    screen = ScreenBrowser()
    adapter = OSAdapter(str(events), screen)
    if not adapter.lab.available():
        print("SUMMARY " + json.dumps({"status": "setup_missing", "commands": os_cell.setup_commands()}))
        return 1
    rows, summary = controls.run(adapter, screen, OUT, k=K, tag="h0-")
    # the provenance channel beside the result: how often the X server's record and the client's claim agree, per condition
    prov = {}
    for r in rows:
        p = (r.get("trigger") or {}).get("provenance") if r["condition"] == "genuine" else None
        prov.setdefault(r["condition"], []).append(p)
    flat = {f"{a}/{act}": f"U={v['U']} CR={v['CR']}" for a, acts in summary["cells"][OSAdapter.cell].items() for act, v in acts.items()}
    print(
        "SUMMARY "
        + json.dumps(
            {"episodes": len(rows), "h0d": summary["h0d"], "cells": flat, "genuine_window_owner_records": [p for p in prov.get("genuine", []) if p][:3]},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
