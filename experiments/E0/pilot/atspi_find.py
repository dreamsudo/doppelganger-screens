"""
File · experiments/E0/pilot/atspi_find.py
Purpose · Pilot tool: locate a marker string in the AT-SPI accessibility tree of the running desktop and report the chain of roles above it, so a desktop application's rendering of foreign content can be classified as L1 (inline in the application's document) or L2 (its own document, frame or embedded node).
Description · Walks every application on the AT-SPI desktop (bounded in nodes and time per application), matches the marker against each node's name and, where the Text interface exists, its text, and prints one JSON line per hit with the ancestor path and the boundary roles crossed (document, frame, embedded, dialog, application). walk_nodes() returns the live nodes too so a caller can read extents. Shaped by 2026-10-18: pyatspi 2.58 is installed and the session bus enumerates the XFCE applications.
Inputs/Outputs · In: argv[1] marker; optional argv[2] substring of the application name to restrict the walk. Out: JSON lines on stdout and a SUMMARY line; exit 0 whether or not the marker is found (absence is a result, not an error).
Depends on · python3-pyatspi (system python), a running at-spi2 registry.
Invariant · Read-only: no action, no focus change, no key or click is sent through AT-SPI.
"""

from __future__ import annotations

import json
import sys
import time

import pyatspi
from gi.repository import GLib

ATSPI_ERRORS = (GLib.Error, RuntimeError, AttributeError, TypeError, ValueError, IndexError)  # a node can vanish or refuse mid-walk
BOUNDARY = {"document web", "document frame", "document", "internal frame", "frame", "embedded", "application", "dialog", "alert", "html container", "window"}
MAX_NODES_PER_APP = 25000
MAX_SECONDS_PER_APP = 20.0


def node_text(n):
    try:
        t = n.queryText()
        return t.getText(0, min(t.characterCount, 4000))
    except ATSPI_ERRORS:
        return ""


def walk_nodes(app, marker):
    """Depth-first walk of one application; hits are (node, record) pairs so the caller can query the live node."""
    hits, seen, skipped, t0 = [], 0, 0, time.time()
    stack = [(app, [])]
    while stack and seen < MAX_NODES_PER_APP and time.time() - t0 < MAX_SECONDS_PER_APP:
        node, path = stack.pop()
        seen += 1
        try:
            role, name = node.getRoleName(), node.name or ""
        except ATSPI_ERRORS:
            skipped += 1
            continue
        here = [*path, (role, name[:60])]
        if marker in name or marker in node_text(node):
            hits.append((node, {"app": here[0][1], "role": role, "name": name[:120], "path": here, "boundaries": [r for r, _ in here if r in BOUNDARY]}))
        try:
            kids = [node.getChildAtIndex(i) for i in range(node.childCount)]
        except ATSPI_ERRORS:
            skipped += 1
            kids = []
        stack.extend((k, here) for k in reversed(kids) if k is not None)
    return hits, seen, skipped, round(time.time() - t0, 2)


def walk(app, marker):
    hits, seen, skipped, secs = walk_nodes(app, marker)
    return [h for _, h in hits], seen, skipped, secs


def main(argv):
    if len(argv) < 2:
        print("usage: atspi_find.py MARKER [APP-NAME-SUBSTRING]", file=sys.stderr)
        return 2
    marker, app_filter = argv[1], (argv[2] if len(argv) > 2 else None)
    desktop = pyatspi.Registry.getDesktop(0)
    apps = [desktop.getChildAtIndex(i) for i in range(desktop.childCount)]
    total_hits, walked = 0, []
    for app in apps:
        if app is None:
            continue
        try:
            aname = app.name or ""
        except ATSPI_ERRORS:
            walked.append({"app": None, "skipped": True})
            continue
        if app_filter and app_filter.lower() not in aname.lower():
            continue
        hits, seen, skipped, secs = walk(app, marker)
        walked.append({"app": aname, "nodes": seen, "skipped": skipped, "seconds": secs, "hits": len(hits)})
        for h in hits:
            print(json.dumps(h, ensure_ascii=False))
        total_hits += len(hits)
    print("SUMMARY " + json.dumps({"marker": marker, "apps_walked": len(walked), "hits": total_hits, "walked": walked}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
