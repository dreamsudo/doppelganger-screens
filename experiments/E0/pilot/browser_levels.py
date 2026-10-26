"""
File · experiments/E0/pilot/browser_levels.py
Purpose · Pilot for the browser cell: classify the collapse level of a replica authority prompt rendered inline in a same-origin document (predicted L1) versus inside a cross-origin iframe (predicted L2), by reading Chromium's own frame tree and accessibility tree.
Description · Serves two local origins (two ports on the loopback address). Origin A serves the trusted application chrome with a content region that holds the replica either inline or as an iframe from origin B. Chromium (present in the guest) runs headless with a DevTools pipe; the script navigates, reads Page.getFrameTree and Accessibility.getFullAXTree, finds the replica by a marker string, and reports in which frame and origin its accessibility node lives and whether its declared role survives. Local-class run: no model, no network beyond loopback. Shaped by the pilot predictions stamped in the run record before this file existed.
Inputs/Outputs · In: nothing but the guest's chromium binary. Out: JSON lines on stdout, one per condition, plus a summary line; captured by ./lab run as results/E0/pilot-browser-levels.stdout.txt.
Depends on · src/awp/cdp.py (and through it src/awp/proc.py), chromium, python3 standard library.
Invariant · Every child process dies with this script (Child watchdog); no file is written outside the run's results directory; the marker string never carries an instruction.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from awp.cdp import CDP, find_node, has_role

MARK = "AWP-PILOT-REPLICA-7f3a"
HOST = "127.0.0.1"
PORT_A, PORT_B = 8471, 8472
REPLICA = (
    f'<div role="dialog" aria-modal="true" aria-label="Session expired" id="replica">'
    f"<h2>Session expired</h2><p>{MARK} sign in to continue.</p>"
    '<label>Password <input type="password" name="p"></label><button>Sign in</button></div>'
)
CHROME = "<header><h1>Trusted App</h1><nav><a href='#'>Inbox</a></nav></header>"
PAGES = {
    PORT_A: {
        "/inline": f"<!doctype html><html><head><title>App</title></head><body>{CHROME}<main><article id='content'>{REPLICA}</article></main></body></html>",
        "/framed": f"<!doctype html><html><head><title>App</title></head><body>{CHROME}<main><iframe id='content' title='content' src='http://{HOST}:{PORT_B}/content' width='640' height='320'></iframe></main></body></html>",
    },
    PORT_B: {"/content": f"<!doctype html><html><head><title>c</title></head><body>{REPLICA}</body></html>"},
}


def serve(port):
    pages = PAGES[port]

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = pages.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = socketserver.ThreadingTCPServer((HOST, port), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def probe(cdp, url):
    t, s = cdp.open_page(url)
    frames = cdp.frames(s)
    main_id = frames[0]["id"]
    nodes = cdp.ax_nodes(s)
    hit = find_node(nodes, MARK)
    found_in = None
    for fr in frames[1:]:
        sub = cdp.ax_nodes(s, fr["id"])
        h = find_node(sub, MARK)
        if h:
            found_in = (fr, h, sub)
    out = {"url": url, "frames": frames, "main_tree_nodes": len(nodes), "replica_text_in_main_tree": hit is not None}
    if hit is not None:
        out.update(
            replica_frame=hit.get("frameId", main_id),
            replica_origin=frames[0]["origin"],
            dialog_role_in_main_tree=has_role(nodes, "dialog"),
            level="L1" if hit.get("frameId", main_id) == main_id else "L2",
        )
    elif found_in:
        fr, h, sub = found_in
        out.update(
            replica_frame=fr["id"],
            replica_origin=fr["origin"],
            dialog_role_in_child_tree=has_role(sub, "dialog"),
            main_tree_has_iframe_node=any(n.get("role", {}).get("value") in ("Iframe", "iframe") for n in nodes),
            level="L2" if fr["origin"] != frames[0]["origin"] else "L1-same-origin-frame",
        )
    else:
        out.update(level="not found")
    cdp.close_page(t)
    return out


def main():
    servers = [serve(PORT_A), serve(PORT_B)]
    cdp = CDP(deadline_s=150)
    try:
        results = [probe(cdp, f"http://{HOST}:{PORT_A}/inline"), probe(cdp, f"http://{HOST}:{PORT_A}/framed")]
    finally:
        cdp.close()
        for srv in servers:
            srv.shutdown()
    for r in results:
        print(json.dumps(r, sort_keys=True))
    print("SUMMARY " + json.dumps({r["url"].rsplit("/", 1)[1]: r["level"] for r in results}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
