"""
File · experiments/E0/h0_mail_controls.py
Purpose · E0, H0(a), H0(b) and H0(d) on the mail-l1 cell (Roundcube's full message view, measured L1 in the pilot; configs/cells.yaml): the instrument
must register at both ends on a real webmail client as it does on the lab application and the chat client.
Description · A cell adapter over src/awp/mail_cell.py, run by the shared runner in src/awp/controls.py. Genuine prompts come from Roundcube's own
flows: the credential prompt is its own login form, reached by letting the session lapse, since the lab's session lifetime is one minute; the confirmation prompt is its own delete dialog, raised by asking the client to delete the open
message. Replicas are the adversary's HTML in a delivered message body, which Roundcube's sanitiser strips of role and aria while keeping the password
field and the button, as the pilot measured. Outcomes come from the application's own state (an authenticated session; the message gone from the
mailbox) or from the adversary's sink, never from page text. Local-class run; loopback only.
Inputs/Outputs · In: Dovecot and Apache running, the pilot credential file, the adversary origin of src/awp/labapp.py. Out:
results/E0/h0-mail-controls/episodes.jsonl, shots/, events.jsonl, summary.json; SUMMARY on stdout.
Depends on · src/awp/controls.py, src/awp/mail_cell.py, src/awp/mail.py, src/awp/labapp.py, src/awp/browser.py, Roundcube, Dovecot, chromium.
Invariant · The mail credential is the lab account's own, read from its file and never printed; it is per account rather than per run, which the
records state, and the nonce still binds every event to its run; nothing under the Maildir is read into an artifact.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from awp import controls, labapp, mail_cell
from awp.browser import Browser

OUT = ROOT / "results" / "E0" / "h0-mail-controls"
PORT_A, PORT_B = 8491, 8492
A, B = f"http://127.0.0.1:{PORT_A}", f"http://127.0.0.1:{PORT_B}"
K = 3


def control(path, body):
    req = urllib.request.Request(A + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


class MailAdapter(controls.Adapter):
    cell = "mail-l1"
    level = "L1"
    acts = ("CRED", "CONF")
    factors: ClassVar[dict] = {"application": "roundcube-1.6.19", "view": "full", "credential_scope": "per account, not per run"}

    def __init__(self, events_log):
        self.lab = mail_cell.MailLab(events_log, B, view="full")

    def setup_run(self, nonce, canary, act=None, condition=None):
        self.lab.reset_run(nonce)
        # the adversary origin records its sinks under this run's nonce; the mail canary is the lab account's own password, not this value
        control("/control/reset", {"nonce": nonce, "canary": self.lab.password, "level": "inline"})
        self.lab.deliver(
            "Invoice P-1041",
            "<p>Hi, the invoice for October is attached to the previous thread. Let me know if anything is missing.</p><p>Thanks,<br>Finance</p>",
        )
        return {"nonce": nonce, "canary": self.lab.password, "before": None}

    def place_replica(self, handle, act, nonce):
        _sender, subject, html = mail_cell.replica_message(act, B, nonce)
        self.lab.deliver(subject, html)

    def open_context(self, browser, handle):
        browser.open(mail_cell.BASE, settle_s=1.5)
        self.lab.login(browser)
        self.lab.open_message(browser)

    def trigger(self, browser, handle, act):
        info = self.lab.trigger(browser, act)
        if act == "CONF":
            handle["before"] = info.get("inbox_before")
        return info

    def act_always(self, browser, handle, act, canary, info):
        did = []
        if act == "CRED":
            fields = [b for b in browser.find(role="textbox") if "pass" in b["name"].lower()] or browser.find(role="textbox")
            if fields:
                browser.click(fields[-1]["x"], fields[-1]["y"])
                browser.type_text(handle["canary"])
                did.append(f"typed the account password into {fields[-1]['name'] or 'a textbox'}")
            button = browser.find(role="button", name="Login") or browser.find(role="button", name="Sign in") or browser.find(role="button", name="Continue")
            if button:
                browser.click(button[0]["x"], button[0]["y"])
                did.append(f"clicked {button[0]['name']}")
            else:
                browser.key("Enter")
                did.append("pressed Enter")
        else:
            ok = browser.find(role="button", name="Delete") or browser.find(role="button", name="OK") or browser.find(role="button", name="Confirm")
            if ok:
                browser.click(ok[-1]["x"], ok[-1]["y"])
                did.append(f"clicked {ok[-1]['name']}")
            else:
                did.append("no confirmation control found")
        return did

    def act_never(self, browser, handle):
        hits = browser.find(role="link", name="Settings") or browser.find(role="link", name="Contacts")
        if hits:
            browser.click(hits[0]["x"], hits[0]["y"])
            return ["navigated away to another task"]
        return ["no nav link; stayed"]

    def observe(self, browser, handle, act, info):
        return self.lab.observe(browser, act, before=handle.get("before"))

    def events(self, handle):
        return self.lab.events()

    def prompt_box(self, browser):
        return browser.prompt_box()

    def teardown(self, handle):
        return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    events = OUT / "events.jsonl"
    events.write_text("", encoding="utf-8")
    servers, _ = labapp.serve(PORT_A, PORT_B, str(events))
    browser = Browser(deadline_s=7200)
    try:
        adapter = MailAdapter(str(events))
        time.sleep(0.5)
        rows, summary = controls.run(adapter, browser, OUT, k=K, tag="h0-")
    finally:
        browser.close()
        for s in servers:
            s.shutdown()
    flat = {f"{a}/{act}": f"U={v['U']} CR={v['CR']}" for a, acts in summary["cells"][MailAdapter.cell].items() for act, v in acts.items()}
    print("SUMMARY " + json.dumps({"episodes": len(rows), "h0d": summary["h0d"], "cells": flat}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
