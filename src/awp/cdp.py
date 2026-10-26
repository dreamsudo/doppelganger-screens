"""
File · src/awp/cdp.py
Purpose · The one DevTools client for driving this guest's Chromium (the method, one of everything): launch headless over --remote-debugging-pipe, send commands, wait for events, read frame trees and accessibility trees.
Description · Chromium reads fd 3 and writes fd 4; messages are NUL-delimited JSON. The fds are renumbered by a shell exec so no preexec_fn is used (thread-safe). The process runs under awp.proc.Child with a deadline. First written inside experiments/E0/pilot/browser_levels.py on 2026-10-18 and moved here when the webmail pilot needed the same client.
Inputs/Outputs · In: a deadline in seconds and optional extra Chromium flags. Out: CDP.call(method, params, session) results as dicts; CDP.wait_event; helpers frames_of() and ax_nodes().
Depends on · src/awp/proc.py, chromium.
Invariant · close() always terminates Chromium; every call has a timeout; no file outside the temporary profile directory is written.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time

from awp.proc import Child

DEFAULT_FLAGS = ("--headless=new", "--remote-debugging-pipe", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--window-size=1280,900")


class CDP:
    def __init__(self, deadline_s, extra_flags=(), start_url="about:blank"):
        r_in, w_in = os.pipe()
        r_out, w_out = os.pipe()
        self.profile = tempfile.mkdtemp(prefix="awp-chromium-")
        flags = [*DEFAULT_FLAGS, f"--user-data-dir={self.profile}", *extra_flags, start_url]
        argv = ["sh", "-c", f'exec chromium "$@" 3<&{r_in} 4>&{w_out}', "chromium", *flags]
        self.child = Child(argv, deadline_s, pass_fds=(r_in, w_out), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(r_in)
        os.close(w_out)
        self.w, self.r = w_in, r_out
        self.buf, self.events, self.next_id = b"", [], 0

    def send(self, method, params=None, session=None):
        self.next_id += 1
        msg = {"id": self.next_id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        os.write(self.w, json.dumps(msg).encode() + b"\0")
        return self.next_id

    def recv(self):
        while b"\0" not in self.buf:
            chunk = os.read(self.r, 65536)
            if not chunk:
                raise RuntimeError("devtools pipe closed")
            self.buf += chunk
        raw, _, self.buf = self.buf.partition(b"\0")
        return json.loads(raw)

    def call(self, method, params=None, session=None, timeout_s=20):
        mid = self.send(method, params, session)
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            m = self.recv()
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})
            self.events.append(m)
        raise TimeoutError(method)

    def wait_event(self, name, session, timeout_s=20):
        t0 = time.time()
        for i, m in enumerate(self.events):
            if m.get("method") == name and m.get("sessionId") == session:
                return self.events.pop(i)
        while time.time() - t0 < timeout_s:
            m = self.recv()
            if m.get("method") == name and m.get("sessionId") == session:
                return m
            self.events.append(m)
        raise TimeoutError(name)

    def open_page(self, url, settle_s=0.5):
        """Create a target, attach, enable Page and Accessibility, navigate, wait for load. Returns (targetId, sessionId)."""
        t = self.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        s = self.call("Target.attachToTarget", {"targetId": t, "flatten": True})["sessionId"]
        self.call("Page.enable", session=s)
        self.call("Accessibility.enable", session=s)
        self.call("Page.navigate", {"url": url}, session=s)
        self.wait_event("Page.loadEventFired", s)
        time.sleep(settle_s)
        return t, s

    def frames(self, session):
        return frames_of(self.call("Page.getFrameTree", session=session)["frameTree"])

    def ax_nodes(self, session, frame_id=None):
        params = {"frameId": frame_id} if frame_id else {}
        try:
            return self.call("Accessibility.getFullAXTree", params, session=session).get("nodes", [])
        except RuntimeError:
            return []

    def close_page(self, target_id):
        self.call("Target.closeTarget", {"targetId": target_id})

    def close(self):
        self.child.stop()


def frames_of(tree, out=None):
    out = out if out is not None else []
    f = tree["frame"]
    out.append({"id": f["id"], "url": f.get("url"), "origin": f.get("securityOrigin"), "parent": f.get("parentId")})
    for c in tree.get("childFrames", []):
        frames_of(c, out)
    return out


def find_node(nodes, marker):
    return next((n for n in nodes if marker in json.dumps(n.get("name", {}))), None)


def has_role(nodes, role):
    return any(n.get("role", {}).get("value") == role for n in nodes)
