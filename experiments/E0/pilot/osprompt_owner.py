"""
File · experiments/E0/pilot/osprompt_owner.py
Purpose · Pilot for the OS-prompt cell: which X11 channel tells a genuine polkit prompt from an unprivileged replica window, and whether the adversary can write it (METHOD.md §3, Corollary 3: the channel must be one the adversary principal cannot write).
Description · Two channels are read for every window: the client-written property _NET_WM_PID (what xdotool getwindowpid reports) and the X server's own record of the creating client's PID (X-Resource extension, QueryClientIds). The probe triggers a genuine prompt with pkexec, then draws an honest replica (a Tk window), then forges the replica's _NET_WM_PID to the agent's PID from a third process with xprop, and reads both channels each time. Shaped by the first run of 2026-10-18, in which the honest replica carried no _NET_WM_PID at all, which showed that the client property is optional and therefore not a provenance channel. Local-class run: no model, no network.
Inputs/Outputs · In: DISPLAY, xdotool, xprop, pkexec, a running polkit agent, python-xlib (venv). Out: JSON lines on stdout; captured by ./lab run as results/E0/pilot-osprompt-owner.stdout.txt.
Depends on · src/awp/proc.py, python-xlib, xdotool, xprop, pkexec.
Invariant · No password is typed; the genuine prompt is cancelled by terminating pkexec and, if it lingers, by Escape; every child dies with this script; the process listing is filtered by command name only so no command line enters the artifact.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from awp.proc import Child

try:
    from Xlib import display as xdisplay
    from Xlib.ext import res as xres
except ImportError:  # the venv's interpreter is required
    xdisplay = xres = None

TK_REPLICA = (
    "import tkinter as tk\n"
    "r=tk.Tk(); r.title('Authentication Required'); r.geometry('420x180')\n"
    "tk.Label(r,text='Authentication is required to run a program as another user').pack(pady=8)\n"
    "tk.Label(r,text='Password:').pack(); tk.Entry(r,show='*').pack(); tk.Button(r,text='Authenticate').pack(pady=8)\n"
    "r.after(25000, r.destroy); r.mainloop()\n"
)


def sh(args, timeout_s=10):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout_s, check=False).stdout


def visible():
    return set(sh(["xdotool", "search", "--onlyvisible", "--name", "."]).split())


def server_pid(wid):
    """The X server's record of the PID of the client that created the window (X-Resource); not writable by clients."""
    if xdisplay is None:
        return None
    d = xdisplay.Display()
    try:
        r = d.res_query_client_ids([{"client": int(wid), "mask": xres.LocalClientPIDMask}])
        pids = [int(v) for iv in r.ids for v in iv.value]
        return pids[0] if pids else None
    finally:
        d.close()


def info(wid):
    name = sh(["xdotool", "getwindowname", wid]).strip()
    claimed = sh(["xdotool", "getwindowpid", wid]).strip()
    cls = sh(["xprop", "-id", wid, "WM_CLASS"]).strip().split("=", 1)[-1].strip()
    spid = server_pid(wid)
    exe = None
    if spid:
        try:
            exe = os.readlink(f"/proc/{spid}/exe")
        except OSError:
            pass
    return {"wid": wid, "name": name, "class": cls, "client_claimed_pid": claimed or None, "server_pid": spid, "server_pid_exe": exe}


def new_windows(before, wait_s=8.0):
    t0 = time.time()
    while time.time() - t0 < wait_s:
        if visible() - before:
            time.sleep(0.8)
            return [info(w) for w in sorted(visible() - before)]
        time.sleep(0.2)
    return []


def main():
    out = {"display": os.environ.get("DISPLAY"), "session": os.environ.get("XDG_SESSION_TYPE"), "xres_available": xdisplay is not None}
    out["polkit_agents_running"] = [ln.strip() for ln in sh(["ps", "-eo", "pid,comm"]).splitlines() if "polkit" in ln.split()[-1]]
    base = visible()
    genuine = Child(["pkexec", "/usr/bin/true"], 30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        out["genuine_windows"] = new_windows(base)
    finally:
        genuine.stop()
    time.sleep(1.0)
    for w in out["genuine_windows"]:
        if w["wid"] in visible():
            sh(["xdotool", "key", "--window", w["wid"], "Escape"])
    time.sleep(0.5)
    agent_pid = next((w["server_pid"] for w in out["genuine_windows"] if w["server_pid"]), None)

    base2 = visible()
    replica = Child([sys.executable, "-c", TK_REPLICA], 30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        honest = new_windows(base2)
        out["replica_honest"] = honest
        forged = []
        if honest and agent_pid:
            for w in honest:  # a third process rewrites the client property to the agent's PID
                sh(["xprop", "-id", w["wid"], "-f", "_NET_WM_PID", "32c", "-set", "_NET_WM_PID", str(agent_pid)])
            time.sleep(0.3)
            forged = [info(w["wid"]) for w in honest]
        out["replica_after_forging_client_property"] = forged
    finally:
        replica.stop()

    g_claim = {w["client_claimed_pid"] for w in out["genuine_windows"]}
    g_srv = {w["server_pid"] for w in out["genuine_windows"]} - {None}
    r_srv = {w["server_pid"] for w in out.get("replica_honest", [])} - {None}
    f_claim = {w["client_claimed_pid"] for w in out.get("replica_after_forging_client_property", [])}
    out["channel_client_property"] = {
        "genuine": sorted(g_claim - {None}),
        "honest_replica": sorted({w["client_claimed_pid"] for w in out.get("replica_honest", [])} - {None}),
        "forged_replica": sorted(f_claim - {None}),
        "omittable": any(w["client_claimed_pid"] is None for w in out.get("replica_honest", [])),
        "forgeable_to_agent_pid": bool(agent_pid) and str(agent_pid) in f_claim,
    }
    out["channel_server_record"] = {
        "genuine": sorted(g_srv),
        "replica": sorted(r_srv),
        "replica_after_forging": sorted({w["server_pid"] for w in out.get("replica_after_forging_client_property", [])} - {None}),
        "distinguishes": bool(g_srv) and bool(r_srv) and not (g_srv & r_srv),
    }
    out["level"] = "L3 via server record" if out["channel_server_record"]["distinguishes"] else "not shown"
    print(json.dumps(out, sort_keys=True))
    print("SUMMARY " + json.dumps({"osprompt": out["level"], "client_property": out["channel_client_property"], "server_record": out["channel_server_record"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
