"""
File · src/awp/desktop.py
Purpose · The one desktop driver for the cells that are not a web page: the accessibility tree of the running X session through AT-SPI,
the window list with each window's owner as the X server itself records it, and actions sent as real input rather than through an application's API.
It is what the Thunderbird, Mattermost-desktop and OS-prompt cells are built on, and it is where the L3 provenance channel of METHOD.md §4 is read.
Description · Accessibility: the AT-SPI desktop is walked application by application, bounded in nodes and in time, and a node is returned with its
role, name, the chain of roles above it and its screen extents, so a caller can click what it found. Gecko and Electron only appear on the bus with
GNOME_ACCESSIBILITY set and renderer accessibility forced, which the callers do. Windows: every mapped window is listed with the client-written
_NET_WM_PID, which the pilot measured to be both omittable and forgeable, and with the X server's own record of the creating client through the
X-Resource extension, which an unprivileged client cannot write; the two are returned side by side so the difference is visible in the record rather
than assumed. Input: pointer and keyboard events go through xdotool, so an application sees ordinary input.
Inputs/Outputs · In: DISPLAY, a running at-spi2 registry, xdotool, xprop, python-xlib in .venv. Out: node and window records; nothing is written.
Depends on · python3-pyatspi (system python), python-xlib (.venv), xdotool, xprop, src/awp/proc.py.
Invariant · Read-only on the accessibility tree: no focus is taken and no action is sent through AT-SPI; actions go through the input path only; a
password is never typed by this module, and the X-Resource owner is read, never written.
"""

from __future__ import annotations

import json
import subprocess
import time

BOUNDARY_ROLES = ("application", "frame", "document web", "document frame", "dialog", "alert", "embedded", "panel")


def sh(args, timeout_s=10):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout_s, check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


# ---------------------------------------------------------------- accessibility
def _extents(node, pyatspi):
    """Screen extents of a node, or None. measured (Thunderbird controls, first run): Gecko exposes extents only through the Component
    interface; the direct call returned nothing for every one of 108 message-list nodes, so nothing could be clicked. The component is tried first."""
    for getter in (lambda n: n.queryComponent().getExtents(pyatspi.DESKTOP_COORDS), lambda n: n.getExtents(pyatspi.DESKTOP_COORDS)):
        try:
            box = getter(node)
        except Exception:  # noqa: BLE001  a node with no component interface has no extents, which is ordinary here
            box = None
        if box is not None and (box.width > 0 or box.height > 0):
            return [box.x, box.y, box.width, box.height]
    return None


def walk(app_fragment=None, match=None, max_nodes=6000, deadline_s=20.0):
    """Every node of the AT-SPI desktop (optionally one application), with its role chain and extents. `match` filters by name or text."""
    import pyatspi

    out, skipped, seen, t0 = [], [], 0, time.time()
    desktop = pyatspi.Registry.getDesktop(0)
    for app in desktop:
        if app is None:
            continue
        name = app.name or ""
        if app_fragment and app_fragment.lower() not in name.lower():
            continue
        stack = [(app, [])]
        while stack and seen < max_nodes and time.time() - t0 < deadline_s:
            node, path = stack.pop()
            seen += 1
            try:
                role = node.getRoleName()
                label = node.name or ""
                text = ""
                try:
                    ti = node.queryText()
                    text = ti.getText(0, min(ti.characterCount, 400))
                except NotImplementedError:
                    pass
                extents = _extents(node, pyatspi)
                hay = f"{label} {text}"
                if match is None or match.lower() in hay.lower():
                    out.append({"app": name, "role": role, "name": label, "text": text[:200], "path": path + [role], "extents": extents, "node": node})
                for child in node:
                    if child is not None:
                        stack.append((child, path + [role]))
            except Exception as e:  # noqa: BLE001  a window closing mid-walk raises; the node is skipped and the reason is kept, never swallowed
                skipped.append(f"{name}: {type(e).__name__}")
                continue
    if skipped:
        out.append(
            {
                "app": "(walk)",
                "role": "note",
                "name": f"{len(skipped)} nodes skipped while the tree changed",
                "text": "; ".join(sorted(set(skipped))[:6]),
                "path": [],
                "extents": None,
                "node": None,
            }
        )
    return out


def find(app_fragment, roles=(), name_fragment=None, **kw):
    """Nodes of an application whose role is one of `roles` and whose name contains `name_fragment`."""
    hits = walk(app_fragment, match=name_fragment, **kw)
    if roles:
        hits = [h for h in hits if h["role"] in roles]
    return hits


def centre(node_record):
    e = node_record.get("extents")
    if not e or e[2] <= 0 or e[3] <= 0:
        return None
    return e[0] + e[2] / 2, e[1] + e[3] / 2


def boundary_chain(node_record):
    """The boundary roles crossed from the application down to this node: the collapse level is read from this chain (METHOD.md §2)."""
    return [r for r in node_record.get("path", []) if r in BOUNDARY_ROLES]


# ---------------------------------------------------------------- input
def click(x, y, button=1):
    sh(["xdotool", "mousemove", str(int(x)), str(int(y)), "click", str(button)], 10)


def type_text(text, delay_ms=25):
    sh(["xdotool", "type", "--delay", str(delay_ms), text], 60)


def key(name):
    sh(["xdotool", "key", name], 10)


# ---------------------------------------------------------------- windows and their owners
def windows():
    """Every mapped window with both owner channels: the client-written property, and the X server's own record of the creating client."""
    ids = [w for w in sh(["xdotool", "search", "--onlyvisible", "--name", ".*"], 15).split() if w.strip()]
    out = []
    for wid in ids:
        name = sh(["xdotool", "getwindowname", wid], 5).strip()
        claimed = sh(["xdotool", "getwindowpid", wid], 5).strip() or None
        out.append(
            {
                "wid": wid,
                "name": name,
                "claimed_pid": int(claimed) if claimed and claimed.isdigit() else None,
                "server_pid": server_pid(wid),
                "wm_class": wm_class(wid),
            }
        )
    return out


def wm_class(wid):
    return sh(["xprop", "-id", wid, "WM_CLASS"], 5).strip().split("=", 1)[-1].strip() or None


def server_pid(wid):
    """The creating client's pid as the X server records it (X-Resource QueryClientIds): a client cannot write this about another client."""
    code = (
        "import sys, json;"
        "from Xlib import display;"
        "from Xlib.ext import res;"
        "d = display.Display();"
        "w = int(sys.argv[1], 0);"
        "ids = res.query_client_ids(d, [res.ClientIdSpec(client=w, mask=res.LocalClientPIDMask)]);"
        "print(json.dumps([list(i.value) for i in ids.ids]))"
    )
    out = sh([".venv/bin/python", "-c", code, wid], 10).strip()
    try:
        vals = json.loads(out)
        return next((v[0] for v in vals if v), None)
    except (ValueError, IndexError):
        return None


def owner_of_window_at(x, y):
    """The window under a point and both of its owner records; the L3 provenance channel of METHOD.md §4 (v)."""
    for w in windows():
        geo = sh(["xdotool", "getwindowgeometry", "--shell", w["wid"]], 5)
        g = dict(line.split("=", 1) for line in geo.splitlines() if "=" in line)
        try:
            wx, wy, ww, wh = int(g["X"]), int(g["Y"]), int(g["WIDTH"]), int(g["HEIGHT"])
        except (KeyError, ValueError):
            continue
        if wx <= x <= wx + ww and wy <= y <= wy + wh:
            return w
    return None
