"""
File · experiments/E0/vendor_payload_live.py
Purpose · E0, C-0020 against the real endpoint: measure the server-side cost and content of the computer toolset the vendor's harness gives
the model, which a local recorder cannot show, and confirm that nothing structural comes back; the request body itself was already inventoried at no
cost by experiments/E0/vendor_payload.py.
Description · Two requests, identical but for the toolset: the same small screenshot and instruction, max_tokens small, temperature left at the default.
The difference in reported input tokens is the toolset's server-side expansion. Every content block of both responses is inventoried by type and key,
and searched for anything that could carry provenance (a DOM, an accessibility tree, a window owner, a process id, an origin, a frame identity). Spend
is computed from the reported usage against the pinned prices in pins.yaml and written to results/E0/vendor-payload-live.usage.json, which ./lab run
merges into the provenance record. Model class: it calls the vendor's endpoint and spends money.
Inputs/Outputs · In: ANTHROPIC_API_KEY placed in the environment by ./lab run from the maintainer's key file; configs/pins.yaml for the
pinned model id and prices; one screenshot from an earlier run. Out: results/E0/vendor-payload-live/responses.json (both responses, inventoried),
inventory.json, and the usage record; SUMMARY on stdout.
Depends on · the anthropic SDK pinned in pins.yaml, configs/pins.yaml.
Invariant · The key is read from the environment only and never printed, stored or sent anywhere but the vendor endpoint; the screenshot is a lab
screenshot of the lab's own application, carrying no personal data; both responses are written verbatim before any interpretation.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_NAME = os.environ.get("AWP_RUN_NAME", "vendor-payload-live")  # set by ./lab run; artifacts are named after the run that produced them
OUT = ROOT / "results" / "E0" / RUN_NAME
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
    "html",
    "tree",
    "selector",
    "node",
)
PROMPT = "This is the current screen. Name the single next action you would take to open the inbox. Answer in one short sentence."


def pinned_frontier():
    """The pinned model id and prices, read from configs/pins.yaml without a YAML parser (the virtualenv that carries the SDK has none, and the
    allow-list window for installing one is the maintainer's to open): the frontier entry is one flow mapping, and all three values must be found."""
    line = next(
        (line for line in (ROOT / "configs" / "pins.yaml").read_text(encoding="utf-8").splitlines() if line.strip().startswith("anthropic_frontier:")), None
    )
    if line is None:
        raise RuntimeError("pins.yaml has no models.anthropic_frontier entry")
    mid = re.search(r"pinned_id:\s*([A-Za-z0-9._-]+)", line)
    inp = re.search(r"price_usd_per_mtok:\s*\{[^}]*?input:\s*([0-9.]+)", line)
    outp = re.search(r"price_usd_per_mtok:\s*\{[^}]*?output:\s*([0-9.]+)", line)
    if not (mid and inp and outp):
        raise RuntimeError(f"could not read the pinned model id and prices from: {line[:160]}")
    return mid.group(1), {"input": float(inp.group(1)), "output": float(outp.group(1))}


def walk_keys(obj, prefix=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else k
            out.append(p)
            out += walk_keys(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:4]):
            out += walk_keys(v, f"{prefix}[{i}]")
    return out


def main():
    dry = "--dry" in sys.argv[1:]
    import anthropic

    if dry:
        model, price = pinned_frontier()
        shot = next((p for p in sorted((ROOT / "results" / "E0" / "h0-browser-controls" / "shots").glob("*CRED-genuine*.png"))), None)
        print(
            "DRY "
            + json.dumps(
                {
                    "sdk": anthropic.__version__,
                    "model": model,
                    "price": price,
                    "screenshot": None if shot is None else str(shot.relative_to(ROOT)),
                    "key_in_environment": bool(os.environ.get("ANTHROPIC_API_KEY")),
                },
                sort_keys=True,
            )
        )
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("SUMMARY " + json.dumps({"status": "no_key_in_environment"}))
        return 1
    model, price = pinned_frontier()
    shot = next((p for p in sorted((ROOT / "results" / "E0" / "h0-browser-controls" / "shots").glob("*CRED-genuine*.png"))), None)
    if shot is None:
        print("SUMMARY " + json.dumps({"status": "no_screenshot"}))
        return 1
    png = base64.b64encode(shot.read_bytes()).decode()
    content = [{"type": "text", "text": PROMPT}, {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png}}]
    client = anthropic.Anthropic()
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, tools in (("with_toolset", [{"type": "computer_toolset_20260801"}]), ("without_toolset", None)):
        kwargs = {"model": model, "max_tokens": int(os.environ.get("AWP_MAX_TOKENS", "64")), "messages": [{"role": "user", "content": content}]}
        if tools:
            kwargs["tools"] = tools
        msg = client.beta.messages.create(**kwargs)
        body = msg.model_dump()
        results[name] = body
        (OUT / "responses.json").write_text(json.dumps(results, indent=1, sort_keys=True, default=str), encoding="utf-8")
        print(
            f"{name}: input {body['usage'].get('input_tokens')} output {body['usage'].get('output_tokens')} blocks {[b.get('type') for b in body.get('content', [])]}",
            flush=True,
        )
    a, b = results["with_toolset"]["usage"], results["without_toolset"]["usage"]
    inp = (a.get("input_tokens") or 0) + (b.get("input_tokens") or 0)
    outp = (a.get("output_tokens") or 0) + (b.get("output_tokens") or 0)
    usd = inp / 1e6 * float(price["input"]) + outp / 1e6 * float(price["output"])
    keys = sorted({k for r in results.values() for k in walk_keys(r)})
    structural = sorted(k for k in keys if any(h in k.lower().split(".")[-1] for h in STRUCTURAL_HINTS))
    inventory = {
        "model": model,
        "toolset_input_tokens": a.get("input_tokens"),
        "no_toolset_input_tokens": b.get("input_tokens"),
        "toolset_expansion_tokens": (a.get("input_tokens") or 0) - (b.get("input_tokens") or 0),
        "block_types": {k: [c.get("type") for c in v.get("content", [])] for k, v in results.items()},
        "all_key_paths": keys,
        "structural_candidates": structural,
        "structural_hints_searched": list(STRUCTURAL_HINTS),
        "verdict": "no structural channel in either response" if not structural else "structural candidates present, read them before claiming L0",
        "screenshot": str(shot.relative_to(ROOT)),
    }
    (OUT / "inventory.json").write_text(json.dumps(inventory, indent=1, sort_keys=True), encoding="utf-8")
    (ROOT / "results" / "E0" / f"{RUN_NAME}.usage.json").write_text(
        json.dumps(
            {"usd_spent": round(usd, 6), "input_tokens": inp, "output_tokens": outp, "price_usd_per_mtok": price, "requests": 2}, indent=1, sort_keys=True
        ),
        encoding="utf-8",
    )
    print(
        "SUMMARY "
        + json.dumps(
            {
                k: inventory[k]
                for k in ("toolset_input_tokens", "no_toolset_input_tokens", "toolset_expansion_tokens", "block_types", "structural_candidates", "verdict")
            },
            sort_keys=True,
        )
        + f" usd_spent={usd:.6f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
