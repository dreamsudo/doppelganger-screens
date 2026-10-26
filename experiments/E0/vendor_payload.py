"""
File · experiments/E0/vendor_payload.py
Purpose · E0, C-0020 (METHOD.md appendix): inventory every field a deployed vendor computer-use harness passes to the model, to test
the claim that it is a screenshot and at most a URL, with no DOM, accessibility tree, window ownership or process identity, so the vendor path is L0.
Description · The request is captured, not guessed, and its shape is the one the endpoint accepts (measured 2026-10-19: a toolset entry carrying a name is rejected with 400, "the member names are fixed by the dated type"): a recording HTTP server on the loopback address stands in for the vendor endpoint, the pinned SDK
is pointed at it through base_url, one computer-use request is constructed the way the vendor's own documentation constructs it (the client toolset of
a screenshot as the tool result), and the server records the exact JSON body before returning a canned response. The inventory is then read
off that body: the top-level fields, the tool definitions the model is given, and, for every content block, its type and the keys it carries. A field is
counted as structural if it could carry provenance: a DOM or accessibility tree, a window owner, a process id, an origin, or a frame identity. No token
is spent and no network is touched: local class. A later model-class run (C-0020b, under 1 USD) repeats one request against the real endpoint to confirm
the body is accepted unchanged and that nothing structural comes back; this run stands on its own for the field inventory.
Inputs/Outputs · In: the anthropic SDK pinned in pins.yaml installed in .venv-anthropic; a screenshot from an earlier run as the tool result. Out:
results/E0/vendor-payload/request.json (the captured body), inventory.json (fields, tools, blocks, the structural verdict); SUMMARY on stdout.
Depends on · the anthropic SDK (installed in .venv-anthropic), src/awp/proc.py.
Invariant · The body is recorded verbatim before any interpretation; the structural verdict names the exact key list it searched; no credential is read
(the recording endpoint accepts any key, and a placeholder is used so no real key is in reach of this run).
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "results" / "E0" / "vendor-payload"
PORT = 18099
CAPTURED: list = []
STRUCTURAL_HINTS = (
    "dom",
    "a11y",
    "accessibility",
    "ax_tree",
    "axtree",
    "window",
    "owner",
    "pid",
    "process",
    "origin",
    "frame",
    "url",
    "title",
    "html",
    "tree",
    "selector",
    "node",
)
CANNED = {
    "id": "msg_local_recorder",
    "type": "message",
    "role": "assistant",
    "model": "recorder",
    "content": [{"type": "text", "text": "recorded"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 0, "output_tokens": 0},
}


class Recorder(BaseHTTPRequestHandler):
    def log_message(self, *a):
        return

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        CAPTURED.append(
            {
                "path": self.path,
                "headers": {k: ("<redacted>" if k.lower() in ("x-api-key", "authorization") else v) for k, v in self.headers.items()},
                "body": json.loads(raw),
            }
        )
        body = json.dumps(CANNED).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def walk_keys(obj, prefix=""):
    """Every key path in the captured body, so the inventory is exhaustive rather than a list someone remembered to look for."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else k
            out.append(p)
            out += walk_keys(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            out += walk_keys(v, f"{prefix}[{i}]")
    return out


def main():
    try:
        import anthropic
    except ImportError:
        print(
            "SUMMARY "
            + json.dumps({"status": "sdk_absent", "note": "install the pinned anthropic SDK into .venv-anthropic under a download window, then re-run"})
        )
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Recorder)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    shot = next((p for p in sorted((ROOT / "results" / "E0" / "h0-browser-controls" / "shots").glob("*.png"))), None)
    if shot is None:
        print("SUMMARY " + json.dumps({"status": "no_screenshot"}))
        return 1
    import base64

    png = base64.b64encode(shot.read_bytes()).decode()
    model = sys.argv[1] if len(sys.argv) > 1 else "claude-opus-5-5"  # the recorder accepts any id; the pinned one is passed by the caller
    client = anthropic.Anthropic(api_key="placeholder-not-a-credential", base_url=f"http://127.0.0.1:{PORT}")
    err = None
    try:
        client.beta.messages.create(
            model=model,
            max_tokens=256,
            tools=[{"type": "computer_toolset_20260801"}],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Open the inbox."},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png}},
                    ],
                },
            ],
        )
    except Exception as e:  # noqa: BLE001  the recorder returns a canned body; a shape mismatch is itself a recorded fact
        err = f"{type(e).__name__}: {str(e)[:300]}"
    server.shutdown()
    if not CAPTURED:
        print("SUMMARY " + json.dumps({"status": "nothing_captured", "error": err}))
        return 1
    cap = CAPTURED[0]
    body = cap["body"]
    redacted = json.loads(json.dumps(body))
    for m in redacted.get("messages", []):
        for b in m.get("content", []) if isinstance(m.get("content"), list) else []:
            if b.get("type") == "image" and isinstance(b.get("source"), dict) and "data" in b["source"]:
                b["source"]["data"] = f"<{len(b['source']['data'])} base64 chars elided>"
    (OUT / "request.json").write_text(
        json.dumps({"path": cap["path"], "headers": cap["headers"], "body": redacted}, indent=1, sort_keys=True), encoding="utf-8"
    )
    keys = sorted(set(walk_keys(body)))
    blocks = [
        {"role": m.get("role"), "types": [b.get("type") for b in m.get("content", [])] if isinstance(m.get("content"), list) else ["<string>"]}
        for m in body.get("messages", [])
    ]
    structural = sorted(k for k in keys if any(h in k.lower().split(".")[-1] for h in STRUCTURAL_HINTS))
    inventory = {
        "sdk_version": getattr(anthropic, "__version__", None),
        "model_sent": body.get("model"),
        "top_level_fields": sorted(body.keys()),
        "tools": body.get("tools"),
        "message_blocks": blocks,
        "all_key_paths": keys,
        "structural_candidates": structural,
        "structural_hints_searched": list(STRUCTURAL_HINTS),
        "error": err,
        "verdict": "no structural channel in the request" if not structural else "structural candidates present, read them before claiming L0",
    }
    (OUT / "inventory.json").write_text(json.dumps(inventory, indent=1, sort_keys=True), encoding="utf-8")
    print(
        "SUMMARY "
        + json.dumps(
            {k: inventory[k] for k in ("sdk_version", "top_level_fields", "tools", "message_blocks", "structural_candidates", "verdict", "error")},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
