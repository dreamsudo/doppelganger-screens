"""
File · experiments/E0/pilot/chat_mattermost.py
Purpose · Pilot for the chat cells on Mattermost: post a replica authority prompt as an ordinary message, render it in the web client through Chromium and in the Electron desktop client, and classify where message content lands (predicted L1: inline in the application document for both) and what markup survives (Markdown only; raw HTML and ARIA escaped).
Description · Starts the lab's Mattermost server under a deadline (awp.mm), bootstraps the admin user, team and channel over the API, posts two messages (a Markdown replica with a sign-in link, and a raw-HTML dialog to test sanitisation), then (1) logs into the web client with headless Chromium (skipping the first-visit landing screen through the web app's own flag), opens the channel, waits for the posts and measures frames, accessibility tree and the rendered DOM around the marker; (2) launches the desktop client with a prepared data directory pointing at the server, logs in by typing into its login form located through AT-SPI, and walks its tree for the marker with raised limits, recording what the walk saw. Local-class run: loopback only. Shaped by the first run of 2026-10-18 (landing screen; large Electron trees).
Inputs/Outputs · In: PostgreSQL running with a database the invoking user owns; the pinned Mattermost tarballs unpacked. Out: JSON line and SUMMARY on stdout; captured by ./lab run as results/E0/pilot-chat-mattermost.stdout.txt.
Depends on · src/awp/mm.py, src/awp/cdp.py, src/awp/proc.py, experiments/E0/pilot/atspi_find.py, chromium, xdotool, python3-pyatspi.
Invariant · The admin credential is typed into the local login forms only and never printed; server and clients die with this script; the desktop client's data directory is temporary.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "src"))
from awp import mm
from awp.cdp import CDP, find_node, has_role
from awp.proc import Child

_spec = importlib.util.spec_from_file_location("atspi_find", HERE / "atspi_find.py")
assert _spec is not None and _spec.loader is not None
atspi_find: Any = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(atspi_find)
atspi_find.MAX_NODES_PER_APP = 80000
atspi_find.MAX_SECONDS_PER_APP = 50.0

MARK = "AWP-PILOT-REPLICA-7f3a"
MD_MESSAGE = f"### Session expired\n\n{MARK} sign in to continue.\n\n[Sign in](http://127.0.0.1:8065/login)  \nPassword: `________`"
HTML_MESSAGE = f'<div role="dialog" aria-modal="true" id="replica" data-awp="{MARK}"><h2>Session expired</h2><p>{MARK}-HTML</p><input type="password"><button>Sign in</button></div>'
DESKTOP = mm.VENDOR / "mattermost-desktop-6.3.1-linux-arm64" / "mattermost-desktop"


def js(cdp, s, expr):
    r = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, session=s, timeout_s=30)
    return r.get("result", {}).get("value")


def sh(args, timeout_s=10):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout_s, check=False).stdout


def web_probe(user, password, team):
    cdp = CDP(deadline_s=240)
    out: dict = {}
    try:
        t, s = cdp.open_page(mm.BASE + "/login", settle_s=2.0)
        cdp.call("Runtime.enable", session=s)
        for _ in range(15):  # the first visit shows a landing screen; the web app's own flag skips it
            url = js(cdp, s, "location.href") or ""
            if "landing" in url:
                js(cdp, s, "localStorage.setItem('__landingPageSeen__','true'); location.href='/login'; true")
                time.sleep(3.0)
                continue
            if js(cdp, s, "!!document.querySelector('#input_loginId') && !!document.querySelector('#input_password-input')"):
                break
            time.sleep(1.0)
        out["login_fields"] = js(cdp, s, "[!!document.querySelector('#input_loginId'), !!document.querySelector('#input_password-input')]")
        js(
            cdp,
            s,
            f"""(function(){{
            function setv(el,v){{ var d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set; d.call(el,v); el.dispatchEvent(new Event('input',{{bubbles:true}})); }}
            setv(document.querySelector('#input_loginId'), {json.dumps(user)}); setv(document.querySelector('#input_password-input'), {json.dumps(password)});
            document.querySelector('#saveSetting').click(); return true }})()""",
        )
        for _ in range(20):
            time.sleep(1.0)
            if "/login" not in (js(cdp, s, "location.href") or ""):
                break
        out["after_login_url"] = js(cdp, s, "location.href")
        cdp.call("Page.navigate", {"url": f"{mm.BASE}/{team}/channels/{mm.CHANNEL}"}, session=s)
        cdp.wait_event("Page.loadEventFired", s, timeout_s=40)
        found = False
        for _ in range(40):
            time.sleep(1.0)
            if js(cdp, s, f"document.body && document.body.innerText.indexOf({json.dumps(MARK)})>=0"):
                found = True
                break
        time.sleep(1.0)
        out["url"] = js(cdp, s, "location.href")
        out["marker_in_page_text"] = found
        frames = cdp.frames(s)
        main_id = frames[0]["id"]
        hit_frame, dialog_role = None, None
        for fr in frames:
            nodes = cdp.ax_nodes(s, None if fr["id"] == main_id else fr["id"])
            if find_node(nodes, MARK):
                hit_frame, dialog_role = fr, has_role(nodes, "dialog")
                break
        out["frames"] = frames
        out["replica_frame_is_main"] = (hit_frame["id"] == main_id) if hit_frame else None
        out["dialog_role_in_tree"] = dialog_role
        out["rendered"] = js(
            cdp,
            s,
            f"""(function(){{
            var M={json.dumps(MARK)}; var posts=[...document.querySelectorAll('.post-message__text')].filter(function(e){{return e.textContent.indexOf(M)>=0}});
            var raw=document.querySelector('#replica'); var htmlpost=posts.find(function(e){{return e.textContent.indexOf(M+'-HTML')>=0}});
            return {{posts_with_marker: posts.length, markdown_heading: !!posts.find(function(e){{return e.querySelector('h3')}}), link: !!posts.find(function(e){{return e.querySelector('a')}}),
                     raw_html_became_element: !!raw, raw_html_post_html_head: htmlpost? htmlpost.innerHTML.slice(0,220) : null,
                     chrome_in_same_document: !!document.querySelector('#channel_view, #channel-header, .channel-header, #sidebar-left')}} }})()""",
        )
        out["level"] = "L1" if out.get("replica_frame_is_main") else ("L2" if hit_frame else "not found")
        cdp.close_page(t)
    finally:
        cdp.close()
    return out


def app_hits(app_fragment, marker):
    desktop = atspi_find.pyatspi.Registry.getDesktop(0)
    found, walked = [], []
    for i in range(desktop.childCount):
        app = desktop.getChildAtIndex(i)
        try:
            name = app.name or ""
        except atspi_find.ATSPI_ERRORS:
            continue
        if app_fragment.lower() not in name.lower():
            continue
        hits, seen, skipped, secs = atspi_find.walk_nodes(app, marker)
        walked.append({"app": name, "nodes": seen, "skipped": skipped, "seconds": secs, "hits": len(hits)})
        for node, hit in hits:
            try:
                ext = node.queryComponent().getExtents(atspi_find.pyatspi.DESKTOP_COORDS)
                hit["extents"] = [int(ext.x), int(ext.y), int(ext.width), int(ext.height)]
            except atspi_find.ATSPI_ERRORS:
                hit["extents"] = None
            found.append(hit)
    return found, walked


def find_role(name_fragment, roles):
    hits, _ = app_hits("Mattermost", name_fragment)
    return next((h for h in hits if h.get("extents") and h["role"] in roles), None)


def click_extents(h, dx=None):
    x, y, w, hh = h["extents"]
    sh(["xdotool", "mousemove", str(x + (dx if dx is not None else max(12, w // 2))), str(y + hh // 2), "click", "1"])
    time.sleep(0.4)


def app_structure(app_fragment, max_nodes=4000):
    """Top-level children of the application with a bounded node count under each: shows whether the server view is exposed."""
    desktop = atspi_find.pyatspi.Registry.getDesktop(0)
    out = []
    for i in range(desktop.childCount):
        app = desktop.getChildAtIndex(i)
        try:
            name = app.name or ""
        except atspi_find.ATSPI_ERRORS:
            continue
        if app_fragment.lower() not in name.lower():
            continue
        for k in range(app.childCount):
            child = app.getChildAtIndex(k)
            try:
                saved = atspi_find.MAX_NODES_PER_APP
                atspi_find.MAX_NODES_PER_APP = max_nodes
                _h, seen, _skipped, secs = atspi_find.walk_nodes(child, "\u0000never")
                atspi_find.MAX_NODES_PER_APP = saved
                out.append({"role": child.getRoleName(), "name": (child.name or "")[:60], "nodes": seen, "seconds": secs})
            except atspi_find.ATSPI_ERRORS:
                out.append({"role": "?", "name": "?", "nodes": 0})
    return out


def desktop_probe(user, password):
    out: dict = {}
    data_dir = tempfile.mkdtemp(prefix="awp-mmdesk-")
    Path(data_dir, "config.json").write_text(
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
    env = dict(os.environ, GNOME_ACCESSIBILITY="1", GTK_MODULES="gail:atk-bridge", NO_AT_BRIDGE="0")
    app = Child(
        [str(DESKTOP), f"--data-dir={data_dir}", "--force-renderer-accessibility", "--no-sandbox"],
        230,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        win = None
        for _ in range(45):
            time.sleep(1.0)
            win = next(iter(sh(["xdotool", "search", "--onlyvisible", "--class", "Mattermost"]).split()), None)
            if win:
                break
        out["window_seen"] = bool(win)
        if win:
            time.sleep(8.0)
            sh(["xdotool", "windowactivate", "--sync", win])
            out["structure_before_login"] = app_structure("Mattermost")
            user_f = pw_f = None
            for _ in range(10):
                user_f = find_role("Email or Username", ("entry", "text"))
                pw_f = find_role("Password", ("password text", "entry", "text"))
                if user_f and pw_f:
                    break
                time.sleep(2.0)
            out["login_entries_found"] = [bool(user_f), bool(pw_f)]
            if user_f and pw_f:
                click_extents(user_f)
                sh(["xdotool", "type", "--delay", "25", user], timeout_s=30)
                click_extents(pw_f)
                sh(["xdotool", "type", "--delay", "25", password], timeout_s=30)
                btn = find_role("Log in", ("push button", "button"))
                out["login_button_found"] = bool(btn)
                if btn:
                    click_extents(btn)
                else:
                    sh(["xdotool", "key", "Return"])
                time.sleep(15.0)
        hits, walked = [], []
        for _ in range(8):
            hits, walked = app_hits("Mattermost", MARK)
            if hits:
                break
            time.sleep(5.0)
        out["structure_after_login"] = app_structure("Mattermost")
        out["walks"] = walked
        chan, _ = app_hits("Mattermost", "Town Square")
        out["channel_name_seen_in_tree"] = bool(chan)
        out["hits"] = hits[:3]
        if hits:
            roles = [r for r, _ in hits[0]["path"]]
            out["boundaries"] = hits[0]["boundaries"]
            out["dialog_role_in_tree"] = "dialog" in roles
            out["level"] = "L1 (message inside the web document of the view)" if "document web" in roles else "L2 (own document node)"
        else:
            out["level"] = "not found"
    finally:
        app.stop()
    return out


def main():
    out: dict = {}
    srv = mm.Server(deadline_s=700)
    try:
        out["server_ready_s"] = srv.wait()
        api = mm.Api()
        boot = api.bootstrap()
        out["bootstrap"] = {k: v for k, v in boot.items() if k != "user"}
        out["posts"] = [api.post(boot["channel_id"], MD_MESSAGE), api.post(boot["channel_id"], HTML_MESSAGE)]
        user, password = mm.credentials()
        out["web"] = web_probe(user, password, mm.TEAM)
        out["desktop"] = desktop_probe(user, password)
    finally:
        srv.stop()
    print(json.dumps(out, sort_keys=True, ensure_ascii=False))
    w, d = out.get("web", {}), out.get("desktop", {})
    print(
        "SUMMARY "
        + json.dumps(
            {
                "mattermost_web": w.get("level"),
                "web_rendered": w.get("rendered"),
                "web_dialog_role": w.get("dialog_role_in_tree"),
                "mattermost_desktop": d.get("level"),
                "desktop_boundaries": d.get("boundaries"),
                "desktop_dialog_role": d.get("dialog_role_in_tree"),
                "desktop_walks": d.get("walks"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
