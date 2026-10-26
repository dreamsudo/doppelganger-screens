"""
File · experiments/E0/pilot/mail_thunderbird.py
Purpose · Pilot for the separated-pane mail cell on Thunderbird: open the delivered replica message in a fresh Thunderbird profile bound to the pilot IMAP account and classify, through the AT-SPI tree, whether the body is rendered in its own document (predicted L2, METHOD.md §4 row Thunderbird) and whether the dialog role survives.
Description · Writes a throwaway profile whose user.js defines the pilot IMAP account (loopback, plain, normal password), launches Thunderbird under a deadline with Gecko accessibility enabled (GNOME_ACCESSIBILITY=1; without it Thunderbird never registers on the AT-SPI bus, measured 2026-10-18), answers the password prompt by typing the pilot credential into the prompt window only (found by its title), locates the message row by its subject in Thunderbird's AT-SPI tree and clicks its on-screen extents, then walks the tree for the marker and reports the ancestor roles (document, internal frame, embedded) above the hit. Local-class run.
Inputs/Outputs · In: Dovecot serving the pilot user; the credential file; DISPLAY. Out: JSON line and SUMMARY on stdout; captured by ./lab run as results/E0/pilot-mail-thunderbird.stdout.txt.
Depends on · src/awp/mail.py, src/awp/proc.py, experiments/E0/pilot/atspi_find.py (imported), thunderbird, xdotool, python3-pyatspi.
Invariant · The password is typed only into a window whose title names a password prompt and never printed; Thunderbird dies with this script; the profile lives in a temporary directory; AT-SPI is read-only here, the click goes through xdotool.
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
from awp.mail import credentials, deliver
from awp.proc import Child

_spec = importlib.util.spec_from_file_location("atspi_find", HERE / "atspi_find.py")
assert _spec is not None and _spec.loader is not None
atspi_find: Any = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(atspi_find)

MARK = "AWP-PILOT-REPLICA-7f3a"
SUBJECT = "Your session has expired"
REPLICA_HTML = (
    "<html><body><p>Hello,</p>"
    f'<div role="dialog" aria-modal="true" aria-label="Session expired" id="replica" data-awp="{MARK}" style="border:1px solid #888;padding:12px;max-width:420px">'
    f"<h2>Session expired</h2><p>{MARK} sign in to continue.</p>"
    '<label>Password <input type="password" name="p"></label> <button>Sign in</button></div>'
    "<p>Regards</p></body></html>"
)


def user_js(user):
    prefs = {
        "mail.accountmanager.accounts": "account1",
        "mail.accountmanager.defaultaccount": "account1",
        "mail.account.account1.server": "server1",
        "mail.account.account1.identities": "id1",
        "mail.server.server1.type": "imap",
        "mail.server.server1.hostname": "127.0.0.1",
        "mail.server.server1.port": 143,
        "mail.server.server1.userName": user,
        "mail.server.server1.name": "AWP pilot",
        "mail.server.server1.socketType": 0,
        "mail.server.server1.authMethod": 3,
        "mail.server.server1.login_at_startup": True,
        "mail.server.server1.check_new_mail": True,
        "mail.identity.id1.useremail": user + "@lab.invalid",
        "mail.identity.id1.fullName": "AWP Pilot",
        "mail.shell.checkDefaultClient": False,
        "mailnews.start_page.enabled": False,
        "app.update.enabled": False,
        "app.update.auto": False,
        "datareporting.policy.dataSubmissionEnabled": False,
        "mail.provider.suppress_dialog_on_startup": True,
        "mail.rights.version": 1,
        "accessibility.force_disabled": 0,
        "mailnews.message_display.disable_remote_image": True,
        "javascript.enabled": False,
    }
    return "\n".join(f"user_pref({json.dumps(k)}, {json.dumps(v)});" for k, v in prefs.items()) + "\n"


def sh(args, timeout_s=10):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout_s, check=False).stdout


def windows_named(fragment):
    return sh(["xdotool", "search", "--onlyvisible", "--name", fragment]).split()


def apps_on_bus():
    desktop = atspi_find.pyatspi.Registry.getDesktop(0)
    names = []
    for i in range(desktop.childCount):
        try:
            names.append(desktop.getChildAtIndex(i).name or "")
        except atspi_find.ATSPI_ERRORS:
            continue
    return names


def tb_hits(marker):
    """Walk every Thunderbird application on the bus for the marker; attach on-screen extents where the Component interface exists."""
    desktop = atspi_find.pyatspi.Registry.getDesktop(0)
    found = []
    for i in range(desktop.childCount):
        app = desktop.getChildAtIndex(i)
        try:
            name = app.name or ""
        except atspi_find.ATSPI_ERRORS:
            continue
        if "thunderbird" not in name.lower():
            continue
        hits, _seen, _skipped, _secs = atspi_find.walk_nodes(app, marker)
        for node, hit in hits:
            try:
                ext = node.queryComponent().getExtents(atspi_find.pyatspi.DESKTOP_COORDS)
                hit["extents"] = [int(ext.x), int(ext.y), int(ext.width), int(ext.height)]
            except atspi_find.ATSPI_ERRORS:
                hit["extents"] = None
            found.append(hit)
    return found


def main():
    user, password = credentials()
    delivered = deliver(SUBJECT, REPLICA_HTML)
    profile = tempfile.mkdtemp(prefix="awp-tb-")
    Path(profile, "user.js").write_text(user_js(user), encoding="utf-8")
    env = dict(os.environ, MOZ_NO_REMOTE="1", GTK_MODULES="gail:atk-bridge", NO_AT_BRIDGE="0", GNOME_ACCESSIBILITY="1")
    out: dict = {"delivered": delivered.name, "profile_prefs": "user.js with IMAP account on 127.0.0.1:143"}
    tb = Child(["thunderbird", "--no-remote", "--profile", profile], 170, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        prompt: str | None = None
        main_win: str | None = None
        for _ in range(60):  # wait for the main window and the password prompt
            time.sleep(1.0)
            main_win = main_win or next(iter(windows_named("Mozilla Thunderbird")), None)
            prompt = next(iter(windows_named("assword")), None)
            if prompt:
                break
        out["main_window_seen"] = bool(main_win)
        out["password_prompt_seen"] = bool(prompt)
        if prompt:
            out["password_prompt_title"] = sh(["xdotool", "getwindowname", prompt]).strip()
            sh(["xdotool", "windowactivate", "--sync", prompt])
            time.sleep(0.5)
            sh(["xdotool", "type", "--window", prompt, "--delay", "20", password], timeout_s=30)
            sh(["xdotool", "key", "--window", prompt, "Return"])
            time.sleep(6.0)
        out["thunderbird_on_atspi_bus"] = any("thunderbird" in a.lower() for a in apps_on_bus())
        subject_hits: list = []
        for _ in range(12):
            subject_hits = [h for h in tb_hits(SUBJECT) if h.get("extents")]
            if subject_hits:
                break
            time.sleep(2.0)
        out["subject_row_found"] = bool(subject_hits)
        out["subject_row_roles"] = [r for r, _ in subject_hits[0]["path"]][-6:] if subject_hits else None
        if subject_hits and main_win:
            x, y, w, h = subject_hits[0]["extents"]
            sh(["xdotool", "windowactivate", "--sync", main_win])
            sh(["xdotool", "mousemove", str(x + max(10, w // 2)), str(y + h // 2), "click", "1"])
            time.sleep(6.0)
        hits_total: list = []
        for _ in range(4):
            hits_total = tb_hits(MARK)
            if hits_total:
                break
            time.sleep(4.0)
        out["hits"] = hits_total[:5]
        if hits_total:
            roles = [r for r, _ in hits_total[0]["path"]]
            out["boundaries_above_replica"] = hits_total[0]["boundaries"]
            doc_like = [r for r in roles if r in ("document web", "document frame", "internal frame", "embedded")]
            out["dialog_role_present"] = "dialog" in roles or hits_total[0]["role"] == "dialog"
            out["level"] = "L2 (own document node)" if doc_like else "L1 (no document boundary above the body)"
        else:
            out["level"] = "not found"
    finally:
        tb.stop()
    print(json.dumps(out, sort_keys=True, ensure_ascii=False))
    print(
        "SUMMARY "
        + json.dumps(
            {
                "thunderbird": out.get("level"),
                "on_bus": out.get("thunderbird_on_atspi_bus"),
                "subject_row": out.get("subject_row_found"),
                "prompt": out.get("password_prompt_seen"),
                "boundaries": out.get("boundaries_above_replica"),
                "dialog_role": out.get("dialog_role_present"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
