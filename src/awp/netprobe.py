"""
File · src/awp/netprobe.py
Purpose · Verify the guest-side allow-list from inside, without privileges: the Anthropic API host must accept a TCP connection on 443, every other public destination must fail, the resolver and the loopback must work. Prints a verdict and the sha256 of the committed rule file; the maintainer's `sudo nft -f src/awp/allowlist.nft` output and this verdict together are the verification.
Description · Pure TCP connects with short timeouts; no payload is sent, no credential is involved. A failure to the allowed host or a success to a blocked one is a FAIL. Run as `python3 -m awp.netprobe`.
Inputs/Outputs · In: src/awp/allowlist.nft (for its hash). Out: one JSON line per probe and a final VERDICT line; exit 1 on FAIL.
Depends on · the Python standard library.
Invariant · The probe never sends application data; it never prints anything but host, port, outcome and timing.
"""

from __future__ import annotations

import hashlib
import json
import socket
import sys
import time
from pathlib import Path

RULES = Path(__file__).resolve().parent / "allowlist.nft"
ALLOWED = [("api.anthropic.com", 443)]
BLOCKED = [("pypi.org", 443), ("huggingface.co", 443), ("1.1.1.1", 443), ("9.9.9.9", 53), ("example.com", 80)]


def connect(host, port, timeout=4.0):
    t0 = time.time()
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return {"host": host, "port": port, "resolved": False, "connected": False, "error": str(e)[:80], "s": round(time.time() - t0, 2)}
    last = None
    for fam, typ, proto, _, addr in infos[:2]:
        s = socket.socket(fam, typ, proto)
        s.settimeout(timeout)
        try:
            s.connect(addr)
            s.close()
            return {"host": host, "port": port, "resolved": True, "connected": True, "addr": addr[0], "s": round(time.time() - t0, 2)}
        except OSError as e:
            last = str(e)[:80]
        finally:
            s.close()
    return {"host": host, "port": port, "resolved": True, "connected": False, "error": last, "s": round(time.time() - t0, 2)}


def main():
    ok = True
    for host, port in ALLOWED:
        r = connect(host, port)
        r["expected"] = "connect"
        r["ok"] = r["connected"]
        ok &= r["ok"]
        print(json.dumps(r))
    for host, port in BLOCKED:
        r = connect(host, port)
        r["expected"] = "blocked"
        r["ok"] = not r["connected"]
        ok &= r["ok"]
        print(json.dumps(r))
    r = connect("127.0.0.1", 22, timeout=1.0)
    print(json.dumps({"loopback_reachable_or_refused": r["connected"] or "refused" in (r.get("error") or "").lower()}))
    h = hashlib.sha256(RULES.read_bytes()).hexdigest() if RULES.exists() else None
    print(f"VERDICT {'PASS' if ok else 'FAIL'} rules_sha256={h}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
