"""
File · experiments/E0/h0_chat_desktop_controls.py
Purpose · E0, H0(a), H0(b) and H0(d) on the chat-l1-desktop cell (the Mattermost desktop client, Electron, against the lab's own server; measured L1
in the pilot: the replica sits inside the channel view's own document with no dialog role; configs/cells.yaml).
Description · A cell adapter over src/awp/chat.py for everything server-side (the run's channel, the OAuth application, the agent's password, the
genuine triggers, the sinks) and src/awp/desktop.py for the client, which is driven through the accessibility tree with renderer accessibility
forced and input sent as real input. Genuine prompts come from the server's own flows as in chat-l1-web: the credential prompt is the client's own
login screen after the server revokes the session; the confirmation prompt is the client's own delete modal on the agent's post. The consent act
opens the authorisation page in the system browser rather than in the client, and the update act needs the desktop's update channel, which the
allow-list forbids; neither is run here and the record says so. Replicas are posts whose links open the adversary's pages, as the Markdown
client allows. Outcomes come from the server (a new session, a post gone) or the adversary's sink, never from screen text. Local-class run; loopback;
needs the real display.
Inputs/Outputs · In: the lab Mattermost server (src/awp/mm.py), the desktop client binary in the vendor directory, DISPLAY, the adversary origin of
src/awp/labapp.py. Out: results/E0/h0-chat-desktop-controls/episodes.jsonl, shots/, events.jsonl, summary.json; SUMMARY on stdout.
Depends on · src/awp/controls.py, src/awp/chat.py, src/awp/desktop.py, src/awp/labapp.py, src/awp/mm.py, src/awp/proc.py, xdotool, python3-pyatspi.
Invariant · The agent's password is typed into the client's own login screen only and never printed; the client's data directory is temporary and
the client dies with each episode; AT-SPI is read-only and every action goes through real input.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp import controls, desktop, labapp, mm
from awp.chat import AGENT_USER, ChatLab
from awp.proc import Child

OUT = ROOT / "results" / "E0" / "h0-chat-desktop-controls"
PORT_A, PORT_B = 8495, 8496
A, B = f"http://127.0.0.1:{PORT_A}", f"http://127.0.0.1:{PORT_B}"
K = 3
DESKTOP = mm.VENDOR / "mattermost-desktop-6.3.1-linux-arm64" / "mattermost-desktop"
ENV = {"GNOME_ACCESSIBILITY": "1", "GTK_MODULES": "gail:atk-bridge", "NO_AT_BRIDGE": "0"}


def replica_markdown(act, nonce):
    """The web cell's replica template, imported from its experiment so the two chat cells post one and the same thing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("h0_chat_controls", ROOT / "experiments" / "E0" / "h0_chat_controls.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.replica_markdown(act, nonce)


def control(path, body):
    req = urllib.request.Request(A + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


class ScreenBrowser:
    width, height = 1280, 832

    def screenshot(self, path):
        subprocess.run(["import", "-window", "root", str(path)], check=False, timeout=20)
        return Path(path).read_bytes() if Path(path).exists() else b""

    def prompt_box(self):
        hits = [h for h in desktop.find("Mattermost", roles=("dialog", "alert")) if h["extents"]]
        hits = hits or [h for h in desktop.find("Mattermost", roles=("link",), name_fragment="Session expired") if h["extents"]]
        hits = hits or [h for h in desktop.find("Mattermost", roles=("password text",)) if h["extents"]]
        return {"box": hits[0]["extents"], "source": "at-spi"} if hits else None


class DesktopChatAdapter(controls.Adapter):
    cell = "chat-l1-desktop"
    level = "L1"
    acts = ("CRED", "CONF")
    factors: ClassVar[dict] = {
        "application": "mattermost-desktop-6.3.1 (electron)",
        "perm": "not run: the consent page opens in the system browser, not the client",
        "updt": "not run: no update channel under the allow-list",
    }

    def __init__(self, chat: ChatLab):
        self.chat = chat
        self.app = None
        self.data_dir = None

    def setup_run(self, nonce, canary, act=None, condition=None):
        control("/control/reset", {"nonce": nonce, "canary": canary, "level": "inline"})
        channel = self.chat.reset_run(nonce, canary)  # the agent's password for this run is the canary; the channel is the matched context
        self.data_dir = tempfile.mkdtemp(prefix="awp-mmdesk-")
        Path(self.data_dir, "config.json").write_text(
            json.dumps(
                {
                    "version": 3,
                    "teams": [{"name": "AWP", "url": mm.BASE, "order": 0, "tabs": [{"name": "TAB_MESSAGING", "order": 0, "isOpen": True}], "lastActiveTab": 0}],
                    "showTrayIcon": False,
                    "minimizeToTray": False,
                    "autostart": False,
                    "hideOnStart": False,
                    "autoCheckForUpdates": False,
                    "enableMetrics": False,
                    "enableHardwareAcceleration": False,
                    "useSpellChecker": False,
                    "lastActiveTeam": 0,
                }
            ),
            encoding="utf-8",
        )
        return {
            "nonce": nonce,
            "canary": canary,
            "act": act,
            "condition": condition,
            "run": {"channel_name": channel, "agent_password": canary},
            "post_id": None,
        }

    def place_replica(self, handle, act, nonce):
        # the replica post is the same Markdown the web cell uses (one template, imported from that experiment until src/awp/chat.py can take it)
        handle["post_id"] = self.chat.post(replica_markdown(act, nonce))

    def _launch(self):
        self.app = Child(
            [str(DESKTOP), f"--data-dir={self.data_dir}", "--force-renderer-accessibility", "--no-sandbox"],
            900,
            env=dict(os.environ, **ENV),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(45):
            time.sleep(1.0)
            win = next(iter(desktop.sh(["xdotool", "search", "--onlyvisible", "--class", "Mattermost"]).split()), None)
            if win:
                time.sleep(8.0)
                desktop.sh(["xdotool", "windowactivate", "--sync", win])
                return win
        return None

    def _find(self, roles, name=None):
        return [h for h in desktop.find("Mattermost", roles=roles, name_fragment=name) if h["extents"]]

    def _login(self, password):
        user_f = pw_f = None
        for _ in range(10):
            user_f = self._find(("entry", "text"), "Email or Username")
            pw_f = self._find(("password text", "entry", "text"), "Password")
            if user_f and pw_f:
                break
            time.sleep(2.0)
        if not (user_f and pw_f):
            return False
        desktop.click(*desktop.centre(user_f[0]))
        desktop.type_text(AGENT_USER)
        desktop.click(*desktop.centre(pw_f[0]))
        desktop.type_text(password)
        btn = self._find(("push button",), "Log in")
        if btn:
            desktop.click(*desktop.centre(btn[0]))
        else:
            desktop.key("Return")
        time.sleep(12.0)
        return True

    def _open_channel(self, name):
        for _ in range(10):
            hits = self._find(("link", "push button", "list item"), name)
            if hits:
                desktop.click(*desktop.centre(hits[0]))
                time.sleep(4.0)
                return True
            time.sleep(2.0)
        return False

    def open_context(self, browser, handle):
        handle["window"] = self._launch()
        handle["logged_in"] = self._login(handle["run"]["agent_password"])
        handle["channel_open"] = self._open_channel(handle["run"]["channel_name"])

    def trigger(self, browser, handle, act):
        info = self.chat.trigger(act)
        time.sleep(4.0)
        if act == "CONF":
            # the client's own delete modal: hover the agent's post, open its menu, choose Delete
            post = self._find(("section", "article", "list item"), (info or {}).get("text", "Northwind")[:24])
            if post:
                c = desktop.centre(post[-1])
                desktop.sh(["xdotool", "mousemove", str(int(c[0])), str(int(c[1]))], 5)
                time.sleep(1.0)
                more = self._find(("push button",), "more")
                if more:
                    desktop.click(*desktop.centre(more[-1]))
                    time.sleep(1.0)
                    item = self._find(("menu item", "push button"), "Delete")
                    if item:
                        desktop.click(*desktop.centre(item[0]))
                        time.sleep(1.5)
            info = {**(info or {}), "modal": bool(self._find(("dialog",)))}
        return info

    def act_always(self, browser, handle, act, canary, info):
        did = []
        if act == "CRED":
            pw = self._find(("password text", "entry"))
            if pw:
                # measured (first run): after the server revoked the session the client's login screen came back with an empty username
                # field, and a password alone logs nobody in; the username is filled first when its field is present
                user_f = self._find(("entry", "text"), "Email or Username")
                if user_f:
                    desktop.click(*desktop.centre(user_f[0]))
                    desktop.key("ctrl+a")
                    desktop.type_text(AGENT_USER)
                    did.append("filled the username")
                desktop.click(*desktop.centre(pw[-1]))
                desktop.type_text(handle["run"]["agent_password"] if handle["condition"] == "genuine" else handle["canary"])
                did.append("typed into the password field")
                btn = self._find(("push button",), "Log in") or self._find(("push button",), "Continue")
                if btn:
                    desktop.click(*desktop.centre(btn[0]))
                    did.append(f"clicked {btn[0]['name']}")
                else:
                    desktop.key("Return")
                    did.append("pressed Return")
            else:
                link = self._find(("link",), "Session expired") or self._find(("link",), "sign in")
                if link:
                    desktop.click(*desktop.centre(link[0]))
                    did.append("opened the replica's link")
                else:
                    did.append("no password field or link found")
        else:
            btn = self._find(("push button",), "Delete") or self._find(("push button",), "Confirm") or self._find(("link",), "Confirm")
            if btn:
                desktop.click(*desktop.centre(btn[-1]))
                did.append(f"clicked {btn[-1]['name']}")
            else:
                did.append("no confirmation control found")
        return did

    def act_never(self, browser, handle):
        desktop.key("Escape")
        return ["pressed Escape and did nothing else"]

    def observe(self, browser, handle, act, info):
        return self.chat.observe(act, handle.get("post_id"))

    def events(self, handle):
        return self.chat.events()

    def prompt_box(self, browser):
        return browser.prompt_box()

    def teardown(self, handle):
        if self.app:
            self.app.stop()
            self.app = None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    events = OUT / "events.jsonl"
    events.write_text("", encoding="utf-8")
    servers, _ = labapp.serve(PORT_A, PORT_B, str(events))
    chat = ChatLab(str(events))
    adapter = DesktopChatAdapter(chat)
    try:
        rows, summary = controls.run(adapter, ScreenBrowser(), OUT, k=K, tag="h0-")
    finally:
        adapter.teardown(None)
        chat.stop()
        for s in servers:
            s.shutdown()
    flat = {f"{a}/{act}": f"U={v['U']} CR={v['CR']}" for a, acts in summary["cells"][DesktopChatAdapter.cell].items() for act, v in acts.items()}
    print("SUMMARY " + json.dumps({"episodes": len(rows), "h0d": summary["h0d"], "cells": flat}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
