"""
File · src/awp/mm.py
Purpose · The one client for the lab's own Mattermost server (the method, one of everything): start it under a deadline, wait for it, bootstrap the first (admin) user, team and channel over the REST API, post messages, and read the pilot credential it generates.
Description · The server binary and configuration live outside the tree (../alpha-vendor/mattermost/mattermost, pinned in pins.yaml vendor.mattermost_server) and listen on the loopback address only; PostgreSQL is reached over its local socket as the invoking user, so no database password exists. The admin credential is generated once, written to a file only the invoking user can read next to the server, and never printed. Shaped by 2026-10-18.
Inputs/Outputs · In: nothing but the running PostgreSQL. Out: a Server handle (.stop()), an API session (token), ids of team, channel and posts.
Depends on · src/awp/proc.py, python3 standard library, the Mattermost tarball unpacked by the maintainer.
Invariant · Loopback only; the credential is returned to the caller and never logged; the server dies with the caller's deadline.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from awp.proc import Child

VENDOR = Path(__file__).resolve().parents[3] / "alpha-vendor" / "mattermost"
SERVER_DIR = VENDOR / "mattermost"
CREDENTIALS = VENDOR / ".pilot-credentials"
BASE = "http://127.0.0.1:8065"
TEAM, CHANNEL = "awp", "town-square"


def credentials():
    if CREDENTIALS.exists():
        user, _, password = CREDENTIALS.read_text(encoding="utf-8").strip().partition(":")
        return user, password
    user, password = "awpadmin", secrets.token_urlsafe(18)
    CREDENTIALS.touch(mode=0o600)
    CREDENTIALS.write_text(f"{user}:{password}\n", encoding="utf-8")
    return user, password


class Server:
    def __init__(self, deadline_s=600):
        self.child = Child(
            [str(SERVER_DIR / "bin" / "mattermost"), "server", "-c", str(SERVER_DIR / "config" / "config.json")],
            deadline_s,
            cwd=str(SERVER_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def wait(self, timeout_s=180):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            try:
                with urllib.request.urlopen(BASE + "/api/v4/system/ping", timeout=5) as r:
                    if json.loads(r.read()).get("status") == "OK":
                        return round(time.time() - t0, 1)
            except (urllib.error.URLError, ConnectionError, OSError, ValueError):
                pass
            if self.child.proc.poll() is not None:
                raise RuntimeError(f"mattermost exited early with {self.child.proc.returncode}")
            time.sleep(1.0)
        raise TimeoutError("mattermost did not answer ping")

    def stop(self):
        self.child.stop()


class Api:
    def __init__(self, token=None):
        self.token = token

    def call(self, method, path, body=None, timeout_s=30):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                return r.status, json.loads(r.read() or b"null"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null"), dict(e.headers)

    def bootstrap(self):
        """First user (becomes system admin), team and channel; idempotent across runs."""
        user, password = credentials()
        st, body, _ = self.call("POST", "/api/v4/users", {"email": user + "@lab.invalid", "username": user, "password": password})
        created = st == 201
        st, body, headers = self.call("POST", "/api/v4/users/login", {"login_id": user, "password": password})
        if st != 200:
            raise RuntimeError(f"login failed: {st} {str(body)[:120]}")
        self.token = headers.get("Token")
        st, team, _ = self.call("GET", f"/api/v4/teams/name/{TEAM}")
        if st != 200:
            st, team, _ = self.call("POST", "/api/v4/teams", {"name": TEAM, "display_name": "AWP", "type": "O"})
        st, channel, _ = self.call("GET", f"/api/v4/teams/{team['id']}/channels/name/{CHANNEL}")
        return {"user_created": created, "team_id": team["id"], "channel_id": channel["id"], "user": user}

    def post(self, channel_id, message, props=None):
        st, body, _ = self.call("POST", "/api/v4/posts", {"channel_id": channel_id, "message": message, "props": props or {}})
        if st != 201:
            raise RuntimeError(f"post failed: {st} {str(body)[:160]}")
        return body["id"]
